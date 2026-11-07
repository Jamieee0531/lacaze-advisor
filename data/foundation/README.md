# LACAZE 数据基建

LACAZE 的全部业务数据：品牌设定与规则，以及门店系统中的客户和消费记录。所有人物、商品、价格、服务和活动均为虚构。

## 文件

### brand/ 品牌

| 文件 | 内容 | 主键 |
|---|---|---|
| `brand.json` | 品牌身份、调性、顾问话术规则 | — |
| `scenarios.json` | 六个场景各自的目标和规则 | `scenario` |
| `products.json` | 六款商品：定位、价格、资格、配货、尺寸、重量、皮料、开合、内部结构、背法、颜色、能装什么、工艺、保养 | `product_id` |
| `services.json` | 门店服务：内容、适用条件、办理方式 | `service_id` |
| `policies.json` | 定价、渠道、配货、客户层级规则 | — |
| `events.json` | 门店活动：时间、地点、参加范围、内容、可约时段、不包含的权益 | `event_id` |
| `calendar.json` | 2026–2027 年节日，农历节日已换算成公历 | `date` + `name` |

### clients/ 客户

| 文件 | 内容 | 主键 |
|---|---|---|
| `clients.json` | 客户身份：称呼、性别、年龄、职业、生日、所属门店、建档日期 | `client_id` |
| `purchases.json` | 逐笔消费记录：商品、颜色、日期、成交价、门店 | `purchase_id` |

关联：`purchases` → `client_id`、`product_id`；`events.featured_products` → `product_id`。

## 约定

1. **一个事实只存一处。** 累计消费和客户层级由 `purchases.json` 计算，规则见 `policies.json`，不手工填写。
2. **null 表示不知道，空列表表示确认没有。** 例如 `birthday: null` 表示没有记录生日；客户在 `purchases.json` 中没有记录，表示确认尚无购买。
3. **ID 用小写英文**，例如 `cl004`、`veronique`、`sv_annual_care`；中文只出现在名称和描述里。
4. **门店统一为 `shanghai_chengyuan`**，即 LACAZE 上海澄园店。
5. **偏好、需求、沟通习惯不在这里**，由模型从对话历史中理解。

## 刻意不提供的信息

品牌不会把以下信息提供给顾问。话术中出现具体内容，即为编造：

- 库存数量、到货时间
- 保值、升值、转售价格
- 折扣、赠品、额外权益
- 其他渠道的价格与真伪判断
