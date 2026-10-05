namespace ECommerceStoreInvoice.Infrastructure.Configuration
{
    internal sealed record MongoDbSettings
    {
        public const string SectionName = "MongoDbSettings";
        public required string ConnectionString { get; init; }
        public required string DatabaseName { get; init; }
        public required string ShoppingCartsCollectionName { get; init; }
        public required string OrdersCollectionName { get; init; }
        public required string ProductVersionsCollectionName { get; init; }
        public required string InvoicesCollectionName { get; init; }
        public required string ClientDataVersionsCollectionName { get; init; }
    }
}
