using MongoDB.Driver;

// Only supplies the client to the unchanged Users readiness policy.
// This adapter does not claim to exercise Users domain repositories.
namespace ECommerceStoreUsers.Infrastructure.Context;
internal sealed class MongoDbContext(IMongoClient client)
{
    public IMongoClient Client { get; } = client;
}
