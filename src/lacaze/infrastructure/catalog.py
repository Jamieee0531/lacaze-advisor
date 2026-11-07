from lacaze.domain.models import Product


class ProductCatalog:
    """Read-only lookup of the six products by product_id."""

    def __init__(self, products: list[Product]):
        self.products = {p.product_id: p for p in products}
        if len(self.products) != len(products):
            raise ValueError("Duplicate catalog product IDs")
