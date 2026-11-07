import unicodedata

from lacaze.domain.models import Product, ProductInformation, ProductQueryResult


def normalize_name(value: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", value.casefold()) if not unicodedata.combining(c)
    ).strip()


class ProductCatalog:
    """Read-only lookup. Supplied case snapshots take precedence over static catalog entries."""

    def __init__(self, products: list[Product]):
        self.products = {p.product_id: p for p in products}
        if len(self.products) != len(products):
            raise ValueError("Duplicate catalog product IDs")

    def query(
        self, names: list[str], requested_fields: list[str], supplied: ProductInformation
    ) -> ProductQueryResult:
        snapshot = self.products | {p.product_id: p for p in supplied.products}
        aliases: dict[str, Product] = {}
        for p in snapshot.values():
            for alias in [p.product_id, p.name, p.name.split()[0]]:
                aliases[normalize_name(alias)] = p
        found: dict[str, Product] = {}
        unknown = []
        for name in names:
            product = aliases.get(normalize_name(name))
            if product:
                found[product.product_id] = product
            else:
                unknown.append(name)
        if not names:
            found = snapshot
        missing = {
            p.product_id: [
                field
                for field in requested_fields
                if field not in Product.model_fields or getattr(p, field, None) is None
            ]
            for p in found.values()
        }
        return ProductQueryResult(
            products=list(found.values()), unknown_names=unknown, unavailable_fields=missing
        )
