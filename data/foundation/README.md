# LACAZE foundation data

All business data for LACAZE: the brand and its rules, and the clients and purchases held in the store system. Every person, product, price, service and event is fictional.

## Files

### brand/

| File | Content | Key |
|---|---|---|
| `brand.json` | Brand identity, tone, advisor speaking rules | n/a |
| `scenarios.json` | Goal and rules of each of the six scenarios | `scenario` |
| `products.json` | Six products: positioning, price, eligibility, allocation, size, weight, leather, closure, interior, carry options, colours, what fits, craft, care | `product_id` |
| `services.json` | Store services: content, conditions, how to arrange | `service_id` |
| `policies.json` | Pricing, channel, allocation and tier rules | n/a |
| `stores.json` | Store name and city | `store_id` |
| `events.json` | Store events: time, place, audience, content, bookable slots, what is not included | `event_id` |
| `calendar.json` | Festivals for 2026–2027, lunar dates converted to the Gregorian calendar | `date` + `name` |

### clients/

| File | Content | Key |
|---|---|---|
| `clients.json` | Identity: salutation, gender, age, occupation, birthday, home store, registration date | `client_id` |
| `purchases.json` | One row per purchase: product, colour, date, price paid, store | `purchase_id` |

References: `purchases` → `client_id`, `product_id`, `store`; `events` → `store`, `featured_products`; `clients` → `home_store`. `lacaze validate-data` checks that every ID exists.

Test cases (`data/cases/`) carry only client, product and event IDs; the content is read from here.

## Conventions

1. **One fact, one place.** Cumulative spend and client tier are computed from `purchases.json` using the rules in `policies.json`, never entered by hand.
2. **`null` means unknown, an empty list means confirmed none.** `birthday: null` means no birthday on record; a client with no rows in `purchases.json` has confirmed no purchases.
3. **IDs are lowercase English** (`cl004`, `veronique`, `sv_annual_care`); Chinese appears only in names and descriptions.
4. **Stores are referenced by ID**; names are in `stores.json`. Currently only `shanghai_chengyuan` (LACAZE Shanghai Chengyuan).
5. **Preferences, needs and communication habits are not stored here.** The model reads them from the conversation history.

## Deliberately withheld

The brand does not give advisors the following. Any specific claim about them in a message counts as fabrication:

- Stock levels and arrival dates
- Resale or investment value
- Discounts, gifts and extra benefits
- Prices or authenticity at other channels
