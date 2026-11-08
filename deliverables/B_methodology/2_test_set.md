# 2. Test set design

The 50 test cases were built in three steps: create the clients, write their conversations, then shape the cases scenario by scenario.

## 2.1 Create the clients

Each existing client has a profile: identity and salutation, relationship with the advisor, needs and preferences, purchase records, and communication habits. Purchases match the store data, and the tier is computed from cumulative spend; anything unknown is marked "not recorded" rather than filled in. The table shows only some fields; full profiles are in Appendix 2.

| Client | Tier | Gender · age | Occupation |
|---|---|---|---|
| Shen Li | VVIP | M · 58 | Company founder |
| Zhang Ning | VIC | F · 50 | Investor |
| Gu Wenxiu | VIC | F · 63 | Retired professor |
| Lin Yue | Core | F · 36 | Finance professional |
| He Lin | Core | F · 39 | Marketing director at a multinational |
| Chen Zhe | Core | M · 42 | Law firm partner |
| Wang Aimi (Emily) | Core | F · 31 | Consultant |
| Zhou Yi | Prospect | M · 33 | Product manager at a tech company |
| Wu Ting | Unclassified | F · 35 | Mid-level manager |
| Xu Anran | Unclassified | F · 27 | Independent designer |
| Li Ming, Zhao Jing, Sun Xiao | New clients | — | No store record; name and salutation only |

## 2.2 Write the conversations

Conversation histories were written from the profiles, so each client's needs and habits come through naturally in what they say. For example, Lin Yue:

> **Profile**: values a light bag for her commute; has more meetings lately and wants a bag that holds work documents; when looking at products, cares about the interior layout and how easy it is to get things out.
>
> **Conversation (C02, excerpt)**
> 林悦：Sablé 最近背得挺多，轻便这一点很好。
> 林悦：不过最近开会多了，想再看一只正式一点的，能放工作文件。
> 林悦：先发两款给我看看吧。我比较在意里面怎么分隔，拿东西方便不方便。

Each case has its own date, and its conversation contains only what happened before that date. Conversations for the same client in different cases are independent of each other.

## 2.3 Shape the cases by scenario

Each scenario has 6 to 9 cases, covering both typical and edge situations:

| Scenario | Cases | Typical | Edge |
|---|---|---|---|
| Birthday and festive greetings | 6 | Birthday greeting (C01), festival greeting (C11) | Client just registered, barely talked (C12); new client with no conversation (C14); no birthday on record and no festival nearby (C15) |
| Product recommendation | 9 | Recommending for stated needs (C02, C03) | Client changes their mind (C16); asks for a spec not in the data (C17); asks for a product not in the catalogue (C21); not eligible to buy (C22) |
| Post-purchase care | 9 | Follow-up and usage requests on a purchased bag (C04, C05) | Suspected fault (C24); angry client (C26); bag bought through a reseller, not covered by store services (C27); client replies only "嗯" (C29) |
| Reactivation | 8 | Reconnecting after a long silence (C06, C30) | Client left negative feedback last time (C33); never contacted (C34); client said "先不考虑" last time (C35) |
| Event invitation | 9 | First invitation tied to interests (C07, C37) | Client not eligible for the event (C38, C40, C43); follow-up asks about arrangements not in the data (C42, C44) |
| Price objection | 9 | Over budget, comparing channels, asking for a discount (C08–C10) | Asking for a discount because of past spend (C47); asking whether the bag holds its value (C49); emotional price comparison (C50) |

Beyond scenarios, client types and conversation forms also vary:

| Dimension | Coverage |
|---|---|
| Clients | All five tiers; 17 cases with male clients; 3 new clients; mixed Chinese and English (C19, C39, C46) |
| Conversations | No conversation (C14, C34); twenty-plus messages jumping between topics (C28); emotional (C26, C33, C50) |

The situation and test intent of all 50 cases are in Appendix 3.
