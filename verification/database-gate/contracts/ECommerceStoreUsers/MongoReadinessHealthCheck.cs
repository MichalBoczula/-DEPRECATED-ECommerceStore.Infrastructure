using ECommerceStoreUsers.Infrastructure.Configuration;
using ECommerceStoreUsers.Infrastructure.Context;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Extensions.Options;
using MongoDB.Bson;
using MongoDB.Driver;

namespace ECommerceStoreUsers.Infrastructure.Health;

internal sealed class MongoReadinessHealthCheck(
    MongoDbContext context,
    IOptions<MongoDbSettings> options) : IHealthCheck
{
    public async Task<HealthCheckResult> CheckHealthAsync(
        HealthCheckContext healthCheckContext,
        CancellationToken cancellationToken = default)
    {
        try
        {
            var admin = context.Client.GetDatabase("admin");
            var hello = await admin.RunCommandAsync<BsonDocument>(
                new BsonDocument("hello", 1), cancellationToken: cancellationToken);

            if (!hello.TryGetValue("setName", out var setName) || !setName.IsString ||
                string.IsNullOrWhiteSpace(setName.AsString) ||
                !hello.TryGetValue("isWritablePrimary", out var primary) || !primary.IsBoolean ||
                !primary.AsBoolean ||
                !hello.TryGetValue("logicalSessionTimeoutMinutes", out _))
            {
                return HealthCheckResult.Unhealthy("MongoDB replica set primary with sessions is unavailable.");
            }

            await context.Client.GetDatabase(options.Value.DatabaseName).RunCommandAsync<BsonDocument>(
                new BsonDocument("ping", 1), cancellationToken: cancellationToken);
            return HealthCheckResult.Healthy();
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception)
        {
            return HealthCheckResult.Unhealthy("MongoDB is unavailable for transactions.");
        }
    }
}
