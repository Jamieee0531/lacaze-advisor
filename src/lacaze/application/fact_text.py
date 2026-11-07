"""Turn foundation records into short Chinese facts, one fact per citable piece."""

from datetime import date

from lacaze.domain.models import Product, SuppliedFact
from lacaze.infrastructure.foundation import Event, Purchase, Service

WEEKDAYS = "一二三四五六日"


def chinese_date(day: date) -> str:
    return f"{day.year}年{day.month}月{day.day}日"


def relative(day: date, today: date) -> str:
    delta = (day - today).days
    if delta == 0:
        return "今天"
    if delta == 1:
        return "明天"
    if delta == -1:
        return "昨天"
    return f"{delta} 天后" if delta > 0 else f"{-delta} 天前"


def short_name(product: Product) -> str:
    return product.name.split()[0]


def _product_field_text(product: Product, field: str) -> str | None:
    """None when the catalog has no value, so the fact is simply absent."""
    value = getattr(product, field)
    if value in (None, []):
        return None
    name = short_name(product)
    match field:
        case "positioning":
            return f"{product.name}：{value}"
        case "price_cny":
            suffix = " 起" if product.price_type == "starting_at" else ""
            return f"{name} 价格：{value:,} 元{suffix}（全国官方门店统一定价）"
        case "allocation_ratio":
            return f"{name} 属于配额作品，配额比例 {value}，规则见配货政策"
        case "dimensions_cm":
            return (
                f"{name} 尺寸：宽 {value.width:g} × 高 {value.height:g} × 深 {value.depth:g} 厘米"
            )
        case "weight_g":
            return f"{name} 重量：约 {value:g} 克"
    labels = {
        "leather": "皮料",
        "closure": "开合",
        "interior": "内部",
        "carry": "背法",
        "colors": "颜色",
        "fits": "能装下",
        "does_not_fit": "装不下",
        "craft_points": "工艺",
        "care_notes": "保养",
    }
    text = "、".join(value) if isinstance(value, list) else value
    return f"{name} {labels[field]}：{text}"


def product_facts(product: Product, fields: list[str]) -> list[SuppliedFact]:
    facts = []
    for field in fields:
        text = _product_field_text(product, field)
        if text:
            facts.append(
                SuppliedFact(fact_id=f"{product.product_id}.{field}", text=text, kind="product")
            )
    return facts


def purchase_fact(purchase: Purchase, product: Product, today: date) -> SuppliedFact:
    when = chinese_date(purchase.purchase_date)
    return SuppliedFact(
        fact_id=purchase.purchase_id,
        text=f"购买记录：{when}购入 {product.name}（{purchase.color}），"
        f"距今 {(today - purchase.purchase_date).days} 天",
        kind="purchase",
    )


def service_fact(service: Service) -> SuppliedFact:
    return SuppliedFact(
        fact_id=service.service_id,
        text=f"{service.name}：{service.description}适用：{service.eligibility}；办理：{service.how}",
        kind="service",
    )


def event_facts(event: Event, store_name: str, today: date) -> list[SuppliedFact]:
    day = date.fromisoformat(event.date)
    when = f"{chinese_date(day)}（星期{WEEKDAYS[day.weekday()]}，{relative(day, today)}）"
    items = {
        "name": f"活动名称：{event.name}",
        "time": f"时间：{when} {event.time}",
        "store": f"地点：{store_name}",
        "audience": f"参加范围：{event.audience}",
        "content": f"内容：{event.content}",
        "appointment": f"接待安排：{event.appointment}",
        "not_included": f"不包含：{'、'.join(event.not_included)}",
        "note": event.note,
    }
    return [
        SuppliedFact(fact_id=f"{event.event_id}.{key}", text=text, kind="event")
        for key, text in items.items()
    ]
