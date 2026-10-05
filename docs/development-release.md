# D/5: development release inventory

[`releases/development.json`](../releases/development.json) selects one already
published set. It does not create Azure resources. Every image is pinned by
manifest digest, with its full source commit, successful publication run and
Linux/amd64 platform. Deploy the recorded bytes; do not resolve `latest`, select
current repository heads or rebuild this set during Terraform apply.

| Application | Source repository / default branch | Published source | Publication run |
| --- | --- | --- | --- |
| Products | ProductsCatalog / master | `cd9d04ae2a82d550b3739492b2a9a3229102e9e1` | [36278532100](https://github.com/MichalBoczula/ProductsCatalog/actions/runs/36278532100) |
| Users | ECommerceStoreUsers / master | `16c1b364df69f1db8b9addb78ff224908a63593c` | [36439106910](https://github.com/MichalBoczula/ECommerceStoreUsers/actions/runs/36439106910) |
| Invoice and Orders | ECommerceStoreInvoice / master | `76512ccf8c521cf3151830312acc5b82d2e31792` | [36797439907](https://github.com/MichalBoczula/ECommerceStoreInvoice/actions/runs/36797439907) |
| Payments | ECommerceStorePayments / main | `9663df14cb10886a32fa7850d1ca51537a3da009` | [36810479764](https://github.com/MichalBoczula/ECommerceStorePayments/actions/runs/36810479764) |
| BFF | ECommerceStoreBFF / master | `369a93914dd3052ba5ae5a85b008c18536076fdf` | [36816259182](https://github.com/MichalBoczula/ECommerceStoreBFF/actions/runs/36816259182) |
| Angular | ecommerce-store-web / master | `b474a4b9cf827e2d833dd072db726c8ed1bef5b9` | [36820545193](https://github.com/MichalBoczula/ecommerce-store-web/actions/runs/36820545193) |
| LiveDocs retained D/4 pin | ECommerceStore.LiveDocs / main | `a11d396ad01f1324569c69483e870fa8b9c23cf7` | [37064030047](https://github.com/MichalBoczula/ECommerceStore.LiveDocs/actions/runs/37064030047) |

The business image digests are also the exact pins in the frontend's selected
[`compose/ecommerce-compose.yml`](https://github.com/MichalBoczula/ecommerce-store-web/blob/b474a4b9cf827e2d833dd072db726c8ed1bef5b9/compose/ecommerce-compose.yml).
Its browser acceptance job passed in the publication run above, using local
SQL Server, native MongoDB replica-set containers and a test-only Stripe fixture.
This is evidence for that local release set, not Azure or real Stripe acceptance.
Fixture commands, mounts, credentials and provider overrides must never enter
cloud configuration.

Infrastructure modules are pinned to published `modules-v0.2.0`, commit
`c50c68e37df85d4728f84989a785f1df79c26b58`, publication
[37349898852](https://github.com/MichalBoczula/ECommerceStore.Infrastructure/actions/runs/37349898852).
The current development root uses local modules; future portfolio roots consume
this tag. D/5 changes no modules and requires no module version bump.

## Contracts and evidence

BFF and Angular independently retain the same Products, Users, Invoice and
Payments OpenAPI checksums and producer image pins. Their original manifests and
Payments' Invoice provenance are copied into `releases/evidence`; the checker
compares them against the selected release. Online verification hashes all eight
consumer OpenAPI files and Payments' Invoice export at their recorded commits.
It checks publication runs/jobs, the module tag and actual registry manifest and
config bytes. Registry snapshots preserve the bytes verified on 2026-10-05;
they are metadata, not downloaded application/report payloads or credentials.

The older Products consumer records omitted `sourceCommit`. D/5 recovers its
full SHA from successful Products publication logs. Invoice's generated Products
client has a Kiota lock describing a localhost Swagger export, without immutable
producer provenance. The selected pair has passing full-stack evidence; record
explicit producer provenance on a later Invoice contract refresh. No unverified
Kiota description hash is represented as an OpenAPI SHA-256.

LiveDocs keeps the existing `releases/livedocs.json` pin. The checker requires
these shared fields to agree, so D/5 cannot silently alter D/4's destroy/reapply
release. Newer LiveDocs publications need a reviewed promotion. No production
report bundles are available in this selected release; `reportBundles` is empty.
Populate bundle checksums only when the later LiveDocs content contract supplies
real versioned inputs. LiveDocs is independent of business API compatibility.

## Angular artifact: separate from its image

The existing web pipeline publishes an Nginx image, not a standalone SWA ZIP.
D/5 records the Angular build commit and its exact final static COPY layer:

- SHA-256: `1dfcccae61a78bd2233898ae0caea823ed6ac91a1a131a717824f99910f8e399`
- Compressed bytes: `352003`; root: `usr/share/nginx/html`; 30 verified files.
- `releases/evidence/frontend-files.json` lists each file's size and SHA-256.
  The release separately pins that inventory's checksum.

This layer is an independently checksummed published Angular artifact contained
in the selected image. Its identity is verified through the parent manifest,
config and final COPY history. It can be recovered without Docker or rebuilding.
The extractor verifies the compressed checksum and every file before writing
into a new directory; it rejects traversal, links, whiteouts and duplicate files.
It copies only Angular output, excluding Nginx's default content and proxy config.

It is **not ready for the planned SWA deployment**. The selected environment
uses `/backend`, and Nginx currently proxies that prefix. SWA Free will serve
static files and the browser must call the public BFF directly. BFF currently
hardcodes `http://localhost:4200` in its CORS policy. D/11 must implement the cloud
BFF URL/origin contract and SPA fallback, publish the new artifact once, then
promote the affected frontend/BFF pins together with matching acceptance evidence.
Do not deploy this unchanged bundle and call the cloud flow working.

## Runtime and configuration inventory

All six ACA apps target HTTP **8080** behind ACA HTTPS ingress. Products, Users
and Invoice images also expose 8081 in metadata; that is not the deployment
port. Angular's legacy Nginx image exposes 80, but Angular is intended for SWA
Free, not a seventh ACA app. Orders and shopping carts belong to Invoice.

| App | Ingress | Startup / liveness | Readiness and actual scope |
| --- | --- | --- | --- |
| Products | Internal | `/health/live` | `/health/ready`: SQL |
| Users | Internal | `/health/live` | `/health/ready`: Mongo |
| Invoice | Internal | `/health/live` | `/health/ready`: Mongo; excludes Products and PDF storage |
| Payments | Internal | `/health/live` | `/health/ready`: Mongo; excludes Invoice and Stripe |
| BFF | External, business entry point | `/health` | `/health`: process only; upstream readiness not implemented |
| LiveDocs | External, documentation only | `/health/live` | `/health/ready`: static host |

Use `ASPNETCORE_URLS=http://+:8080` and `ASPNETCORE_ENVIRONMENT=Production` for
.NET apps. ACA ingress terminates HTTPS; audit forwarding and Invoice's
`UseHttpsRedirection` under D/9. Do not invent a `/health/ready` route for BFF or
count liveness as proof that checkout dependencies work.

The following are **setting names and bindings**, not deployment credentials.
D/8-D/9 must resolve them from provisioned resources/secret references. Never
copy localhost URLs or Compose credentials into Azure.

| App | Required cloud overrides | Binding / owner |
| --- | --- | --- |
| Products | `ConnectionStrings__ProductCatalogDb` | SQL connection secret; provisioned SQL database, D/8 |
| Products | `Database__ApplyMigrations` | `false` on normal replicas; one-shot migration/seed strategy, D/10 |
| Users | `MongoDbSettings__ConnectionString`, `MongoDbSettings__DatabaseName` | Mongo secret and Users database, D/8; native transaction/session/index semantics must pass D/6 |
| Invoice | `MongoDbSettings__ConnectionString`, `MongoDbSettings__DatabaseName` | Mongo secret and Invoice database, D/8 |
| Invoice | `ExternalServices__ProductCatalog__BaseUrl` | Internal Products ACA service URL, D/9 |
| BFF | `GatewaySettings__BaseUrl` | BFF's own service base URL; resolve explicitly, D/9 |
| BFF | `ReverseProxy__Clusters__products-cluster__Destinations__destination1__Address` | Internal Products ACA URL |
| BFF | `ReverseProxy__Clusters__users-cluster__Destinations__destination1__Address` | Internal Users ACA URL |
| BFF | `ReverseProxy__Clusters__orders-cluster__Destinations__destination1__Address` | Internal Invoice ACA URL, including Orders |
| BFF | `ReverseProxy__Clusters__payments-cluster__Destinations__destination1__Address` | Internal Payments ACA URL |
| Payments | `PAYMENTS_ENVIRONMENT` | `development` for dev; `production` for portfolio |
| Payments | `PAYMENTS_MONGODB_CONNECTION_STRING`, `PAYMENTS_MONGODB_DATABASE_NAME` | Mongo secret and Payments database, D/8 |
| Payments | `PAYMENTS_ORDERS_API_BASE_URL` | Internal Invoice ACA URL; this is not Products or BFF |
| Payments | `PAYMENTS_STRIPE_ENABLED` | `false` until D/13 provisions the real Stripe test integration |
| Payments | `PAYMENTS_STRIPE_SECRET_KEY`, `PAYMENTS_STRIPE_WEBHOOK_SECRET` | Test-mode Stripe and endpoint signing secrets, D/13 |
| Payments | `PAYMENTS_STRIPE_SUCCESS_URL`, `PAYMENTS_STRIPE_CANCEL_URL` | Fixed HTTPS SWA `/orders?checkout=success` / `/orders?checkout=cancel` URLs, D/11-D/13 |
| LiveDocs | None | No API/database/blob runtime access; image contains the static site |
| Angular | BFF base URL and routing | Build/runtime configuration contract requires application changes under D/11; no Azure secrets in the bundle |

Image defaults can retain the following collection settings when those exact
names are intended; use separate service databases. No collection aliases or
single-store substitutions are assumed.

| Service | Database default | Collection configuration keys = defaults |
| --- | --- | --- |
| Users | `ecommerce-store-users-db` | Under `MongoDbSettings__`: `CustomerCollectionName=customers`, `CustomersHistoryCollectionName=customers-history`, `AdminCollectionName=admins`, `AdminsHistoryCollectionName=admins-history`, `FavoriteCollectionName=favorites` |
| Invoice | `ecommerce-store-invoice-db` | Under `MongoDbSettings__`: `ShoppingCartsCollectionName=shopping-carts`, `OrdersCollectionName=orders`, `ProductVersionsCollectionName=product-versions`, `InvoicesCollectionName=invoices`, `ClientDataVersionsCollectionName=client-data-versions` |
| Payments | `ecommerce_store_payments` | `PAYMENTS_MONGODB_PAYMENTS_COLLECTION_NAME=payments`, `PAYMENTS_MONGODB_PAYMENT_HISTORY_COLLECTION_NAME=payment_history`, `PAYMENTS_MONGODB_WEBHOOK_COLLECTION_NAME=stripe_webhooks`; all three names must differ |

Payments also exposes `PAYMENTS_MONGODB_PROBE_TIMEOUT_SECONDS=5`,
`PAYMENTS_MONGODB_SERVER_SELECTION_TIMEOUT_MS=5000`,
`PAYMENTS_ORDERS_API_TIMEOUT_SECONDS=5`, `PAYMENTS_STRIPE_TIMEOUT_SECONDS=5`
and `PAYMENTS_APP_NAME` (display name). Leave defaults unless justified by cloud
measurement; never weaken Mongo readiness to fit an incompatible free offer.

Invoice includes Chromium/Playwright and needs cloud memory/shared-memory
validation in D/9. Its current `file://` PDF storage is instance-local; D/12 must
implement blob persistence. Product photo storage is also D/12; no imaginary
blob setting is recorded for an adapter that does not exist yet.

Payments fulfillment uses the same pinned Payments image, with command
`python -m ecommerce_store_payments.infrastructure.persistence.mongodb.fulfill_payments --limit 100`.
D/14 supplies the bounded job and configuration; no separate Orders app/image
or additional Stripe provider call is needed for that replay path.

Source inventory: .NET `src/<service>.API/Program.cs` and `appsettings.json`,
service Dockerfiles, Payments
`src/ecommerce_store_payments/infrastructure/config/settings.py` and
`api/routes/health.py`, BFF `Program.cs`/YARP clusters, and web `Dockerfile`,
`nginx.conf`, `src/environments/environment.ts` at the exact commits above.
The repository/commit fields in the manifest are the authoritative source refs.

## Check and reuse

From the Infrastructure repository root:

```bash
python3 scripts/check-development-release.py
python3 -m unittest discover -s tests -v
# Optional public recheck; downloads metadata/static assets, never deploys:
python3 scripts/verify-development-release.py
# Given the downloaded, pinned compressed frontend layer:
python3 scripts/extract-frontend.py frontend-static-layer.tar.gz angular-output
```

The normal PR gate is offline, credential-free and checks metadata consistency.
Public verification additionally needs Docker Hub and GitHub availability;
rate limits or a removed digest fail the check rather than choose a replacement.
Registry digests identify bytes but do not guarantee indefinite retention or
provide signatures. Retain selected images in Docker Hub. Source/provenance
records are reviewable evidence, not a claim of signed supply-chain attestation.

D/15 must consume this manifest rather than invent a second image map. D/16
promotes a reviewed compatible set as a whole. D/17 supplies cloud business
smoke; D/19 supplies full apply/destroy/reapply and residual-cost evidence.
D/6 is the next database gate. D/4 live acceptance remains separately pending.
