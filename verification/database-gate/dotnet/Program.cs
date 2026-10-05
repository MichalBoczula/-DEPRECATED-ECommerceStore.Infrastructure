using System.Text.Json;
using Dapper;
using Microsoft.Data.SqlClient;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Extensions.Options;
using MongoDB.Bson;
using MongoDB.Driver;

internal static class Program
{
    private static readonly Dictionary<string, bool> Checks = new();
    private static void Require(bool value) { if (!value) throw new InvalidOperationException(); }
    private static async Task Check(string name, Func<Task> action)
    {
        try { await action(); Checks[name] = true; }
        catch (Exception) { Checks[name] = false; } // Never publish connection strings or exception messages.
    }
    private static string Env(string name) => Environment.GetEnvironmentVariable(name) ?? throw new InvalidOperationException();
    public static async Task<int> Main(string[] args)
    {
        if (args.Length != 2 || args[0] is not ("azure-candidate" or "native-baseline"))
        { Console.Error.WriteLine("Usage: DatabaseGate azure-candidate|native-baseline report.json"); return 2; }
        await Check("endpoint_identity_and_tls", () =>
        {
            var sql = new SqlConnectionStringBuilder(Env("D6_SQL_CONNECTION_STRING"));
            var mongo = MongoClientSettings.FromConnectionString(Env("D6_MONGO_CONNECTION_STRING"));
            if (args[0] == "azure-candidate")
            {
                Require(sql.DataSource == Env("D6_SQL_HOST") && sql.InitialCatalog == "products-gate");
                Require(sql.Encrypt.ToString() is "True" or "Mandatory" or "Strict" && !sql.TrustServerCertificate);
                Require(mongo.UseTls && !mongo.AllowInsecureTls && mongo.Servers.All(s => s.Host == Env("D6_MONGO_HOST")));
            }
            else
            {
                Require(sql.DataSource == "127.0.0.1,1433" && sql.InitialCatalog == "master");
                Require(mongo.Servers.All(s => s.Host == "127.0.0.1" && s.Port == 27017));
            }
            return Task.CompletedTask;
        });
        if (Checks["endpoint_identity_and_tls"])
        {
            await Check("mongo_suite_setup", Mongo);
            await Check("sql_suite_setup", Sql);
        }
        var passed = Checks.Count > 2 && Checks.Values.All(x => x);
        await File.WriteAllTextAsync(args[1], JsonSerializer.Serialize(new
        {
            backend = args[0], passed, backendSelected = false,
            drivers = new { mongo = "3.7.1", efSqlServer = "10.0.1", dapper = "2.1.66" }, checks = Checks
        }, new JsonSerializerOptions { WriteIndented = true }));
        Console.WriteLine($".NET database gate: {(passed ? "PASS" : "FAIL")}; redacted report written.");
        return passed ? 0 : 1;
    }
    private static async Task Mongo()
    {
        var settings = MongoClientSettings.FromConnectionString(Env("D6_MONGO_CONNECTION_STRING"));
        settings.ServerSelectionTimeout = TimeSpan.FromSeconds(30);
        settings.ConnectTimeout = TimeSpan.FromSeconds(30);
        settings.SocketTimeout = TimeSpan.FromSeconds(60);
        using var client = new MongoClient(settings);
        var name = "d6_gate_" + Guid.NewGuid().ToString("N");
        var db = client.GetDatabase(name);
        try
        {
            await Check("users_readiness_unchanged", async () =>
            {
                var options = Options.Create(new ECommerceStoreUsers.Infrastructure.Configuration.MongoDbSettings
                {
                    ConnectionString = Env("D6_MONGO_CONNECTION_STRING"), DatabaseName = name,
                    CustomerCollectionName = "customers", CustomersHistoryCollectionName = "customer_history",
                    AdminCollectionName = "admins", AdminsHistoryCollectionName = "admin_history", FavoriteCollectionName = "favorites"
                });
                var check = new ECommerceStoreUsers.Infrastructure.Health.MongoReadinessHealthCheck(
                    new ECommerceStoreUsers.Infrastructure.Context.MongoDbContext(client), options);
                Require((await check.CheckHealthAsync(new HealthCheckContext())).Status == HealthStatus.Healthy);
            });
            await Check("invoice_readiness_unchanged", async () =>
            {
                var options = Options.Create(new ECommerceStoreInvoice.Infrastructure.Configuration.MongoDbSettings
                {
                    ConnectionString = Env("D6_MONGO_CONNECTION_STRING"), DatabaseName = name,
                    ShoppingCartsCollectionName = "carts", OrdersCollectionName = "orders", ProductVersionsCollectionName = "versions",
                    InvoicesCollectionName = "invoices", ClientDataVersionsCollectionName = "client_versions"
                });
                var check = new ECommerceStoreInvoice.Infrastructure.Health.MongoReadinessHealthCheck(client, options);
                Require((await check.CheckHealthAsync(new HealthCheckContext())).Status == HealthStatus.Healthy);
            });
            await Check("application_index_shapes", async () =>
            {
                // Index keys mirror Users/Invoice initializers; domain serialization
                // and complete API behavior remain separate application acceptance.
                var patterns = new (string Collection, string Name, string[] Keys, bool Unique, bool LastDescending)[]
                {
                    ("customers", "UX_Customer_ExternalId", ["ExternalId"], true, false),
                    ("customers", "IX_Customer_Companies_TaxId", ["Companies.TaxId"], false, false),
                    ("customer_history", "IX_CustomersHistory_CustomerId", ["CustomerId"], false, false),
                    ("admins", "UX_Admin_ExternalId", ["ExternalId"], true, false),
                    ("admin_history", "IX_AdminHistory_AdminId", ["AdminId"], false, false),
                    ("favorites", "UX_Favorite_ClientId_ProductId", ["ClientId", "ProductId"], true, false),
                    ("carts", "UX_ShoppingCart_ClientId", ["ClientId"], true, false),
                    ("invoices", "UX_Invoice_OrderId", ["OrderId"], true, false),
                    ("client_versions", "IX_ClientDataVersion_ClientId_CreatedAtDesc", ["ClientId", "CreatedAt"], false, true)
                };
                foreach (var pattern in patterns)
                {
                    var collection = db.GetCollection<BsonDocument>(pattern.Collection);
                    var key = new BsonDocument();
                    for (var i = 0; i < pattern.Keys.Length; i++) key.Add(pattern.Keys[i], pattern.LastDescending && i == pattern.Keys.Length - 1 ? -1 : 1);
                    await collection.Indexes.CreateOneAsync(new CreateIndexModel<BsonDocument>(key,
                        new CreateIndexOptions { Name = pattern.Name, Unique = pattern.Unique }));
                    if (!pattern.Unique) continue;
                    var fields = new BsonDocument(pattern.Keys.Select(k => new BsonElement(k, "probe")));
                    await collection.InsertOneAsync(fields);
                    var duplicate = new BsonDocument(pattern.Keys.Select(k => new BsonElement(k, "probe")));
                    try { await collection.InsertOneAsync(duplicate); throw new InvalidOperationException(); }
                    catch (MongoWriteException e) when (e.WriteError.Code == 11000) { }
                }
            });
            var current = db.GetCollection<BsonDocument>("current");
            var history = db.GetCollection<BsonDocument>("history");
            var third = db.GetCollection<BsonDocument>("orders");
            await Check("unique_indexes_and_standard_uuid", async () =>
            {
                await current.Indexes.CreateOneAsync(new CreateIndexModel<BsonDocument>(Builders<BsonDocument>.IndexKeys.Ascending("order_id"), new CreateIndexOptions { Unique = true }));
                var id = new BsonBinaryData(Guid.NewGuid(), GuidRepresentation.Standard);
                await current.InsertOneAsync(new BsonDocument { { "_id", "unique" }, { "order_id", id }, { "version", 1 } });
                var doc = await current.Find(new BsonDocument("_id", "unique")).SingleAsync();
                Require(doc["order_id"].AsBsonBinaryData.SubType == BsonBinarySubType.UuidStandard);
                try { await current.InsertOneAsync(new BsonDocument { { "_id", "duplicate" }, { "order_id", id } }); throw new InvalidOperationException(); }
                catch (MongoWriteException e) when (e.WriteError.Code == 11000) { }
                await history.InsertOneAsync(new BsonDocument("_id", "existing-history"));
                await third.InsertOneAsync(new BsonDocument("_id", "existing-order"));
            });
            await Check("multi_collection_commit", async () =>
            {
                using var session = await client.StartSessionAsync(); session.StartTransaction();
                await current.InsertOneAsync(session, new BsonDocument { { "_id", "commit" }, { "order_id", "commit" }, { "version", 1 } });
                await history.InsertOneAsync(session, new BsonDocument("_id", "commit"));
                await third.InsertOneAsync(session, new BsonDocument("_id", "commit"));
                await session.CommitTransactionAsync();
                Require(await current.CountDocumentsAsync(new BsonDocument("_id", "commit")) == 1 &&
                    await history.CountDocumentsAsync(new BsonDocument("_id", "commit")) == 1 && await third.CountDocumentsAsync(new BsonDocument("_id", "commit")) == 1);
            });
            await Check("multi_collection_history_failure_rollback", async () =>
            {
                using var session = await client.StartSessionAsync(); session.StartTransaction();
                try
                {
                    await current.UpdateOneAsync(session, new BsonDocument("_id", "commit"), new BsonDocument("$set", new BsonDocument("version", 2)));
                    await third.InsertOneAsync(session, new BsonDocument("_id", "rollback"));
                    await history.InsertOneAsync(session, new BsonDocument("_id", "existing-history"));
                    throw new InvalidOperationException();
                }
                catch (MongoWriteException e) when (e.WriteError.Code == 11000) { await session.AbortTransactionAsync(); }
                Require((await current.Find(new BsonDocument("_id", "commit")).SingleAsync())["version"].AsInt32 == 1 &&
                    await third.CountDocumentsAsync(new BsonDocument("_id", "rollback")) == 0);
            });
            await Check("optimistic_concurrency_and_history", async () =>
            {
                var winners = 0;
                async Task Attempt(string suffix)
                {
                    using var session = await client.StartSessionAsync(); session.StartTransaction();
                    try
                    {
                        var result = await current.UpdateOneAsync(session, new BsonDocument { { "_id", "commit" }, { "version", 1 } },
                            new BsonDocument("$set", new BsonDocument("version", 2)));
                        if (result.ModifiedCount != 1) { await session.AbortTransactionAsync(); return; }
                        await history.InsertOneAsync(session, new BsonDocument("_id", "race-" + suffix));
                        await session.CommitTransactionAsync(); Interlocked.Increment(ref winners);
                    }
                    catch (MongoException e) when (e.HasErrorLabel("TransientTransactionError"))
                    { if (session.IsInTransaction) await session.AbortTransactionAsync(); }
                }
                await Task.WhenAll(Attempt("a"), Attempt("b"));
                Require(winners == 1 && await history.CountDocumentsAsync(new BsonDocument("_id", new BsonDocument("$regex", "^race-"))) == 1);
            });
        }
        finally { await Check("dotnet_mongo_cleanup", () => client.DropDatabaseAsync(name)); }
    }
    private static async Task Sql()
    {
        var schema = "d6_" + Guid.NewGuid().ToString("N"); // Owned isolated objects; never drop an application database.
        await using var connection = new SqlConnection(Env("D6_SQL_CONNECTION_STRING"));
        await connection.OpenAsync();
        var options = new DbContextOptionsBuilder<GateContext>().UseSqlServer(Env("D6_SQL_CONNECTION_STRING")).Options;
        try
        {
            await connection.ExecuteAsync($"CREATE SCHEMA [{schema}]");
            await connection.ExecuteAsync($"CREATE TABLE [{schema}].[Widgets] (Id int NOT NULL PRIMARY KEY, Tag nvarchar(100) NOT NULL UNIQUE, Version int NOT NULL)");
            await Check("sql_ef_commit_and_dapper_readback", async () =>
            {
                await using var db = new GateContext(options, schema);
                await using var transaction = await db.Database.BeginTransactionAsync();
                db.Widgets.Add(new Widget { Id = 1, Tag = "one", Version = 1 });
                await db.SaveChangesAsync(); await transaction.CommitAsync();
                Require(await connection.QuerySingleAsync<int>($"SELECT Version FROM [{schema}].[Widgets] WHERE Id=1") == 1);
            });
            await Check("sql_transaction_rollback", async () =>
            {
                await using var db = new GateContext(options, schema);
                await using var transaction = await db.Database.BeginTransactionAsync();
                db.Widgets.Add(new Widget { Id = 2, Tag = "rollback", Version = 1 });
                await db.SaveChangesAsync(); await transaction.RollbackAsync();
                Require(await connection.QuerySingleAsync<int>($"SELECT COUNT(*) FROM [{schema}].[Widgets] WHERE Id=2") == 0);
            });
            await Check("sql_unique_constraint", async () =>
            {
                try { await connection.ExecuteAsync($"INSERT INTO [{schema}].[Widgets] VALUES (3,'one',1)"); throw new InvalidOperationException(); }
                catch (SqlException e) when (e.Number is 2601 or 2627) { }
            });
            await Check("sql_ef_optimistic_concurrency", async () =>
            {
                await using var first = new GateContext(options, schema);
                await using var second = new GateContext(options, schema);
                var a = await first.Widgets.SingleAsync(x => x.Id == 1);
                var b = await second.Widgets.SingleAsync(x => x.Id == 1);
                a.Version = b.Version = 2; await first.SaveChangesAsync();
                try { await second.SaveChangesAsync(); throw new InvalidOperationException(); }
                catch (DbUpdateConcurrencyException) { }
                Require(await connection.QuerySingleAsync<int>($"SELECT Version FROM [{schema}].[Widgets] WHERE Id=1") == 2);
            });
        }
        finally
        {
            await Check("sql_cleanup", async () =>
            {
                await connection.ExecuteAsync($"DROP TABLE IF EXISTS [{schema}].[Widgets]");
                await connection.ExecuteAsync($"IF SCHEMA_ID('{schema}') IS NOT NULL EXEC('DROP SCHEMA [{schema}]')");
            });
        }
    }
}
internal sealed class Widget { public int Id { get; set; } public string Tag { get; set; } = ""; public int Version { get; set; } }
internal sealed class GateContext(DbContextOptions<GateContext> options, string schema) : DbContext(options)
{
    public DbSet<Widget> Widgets => Set<Widget>();
    protected override void OnModelCreating(ModelBuilder model)
    {
        model.Entity<Widget>().ToTable("Widgets", schema);
        model.Entity<Widget>().Property(x => x.Id).ValueGeneratedNever();
        model.Entity<Widget>().Property(x => x.Version).IsConcurrencyToken();
    }
}
