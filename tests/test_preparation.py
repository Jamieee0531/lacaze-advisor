import pytest

from lacaze.application.preparation import prepare
from lacaze.domain.models import ClientInformation, ProductInformation


def by_id(cases):
    return {c.case_id: c for c in cases}


def kinds(pack):
    return {f.kind for f in pack.facts}


def test_tier_and_spend_are_computed_from_purchases(data, cases):
    expected = {"cl001": ("Unclassified", 0), "cl002": ("Core", 77000), "cl004": ("VIC", 303000)}
    for case in cases:
        pack = prepare(case, data)
        if pack.client.client_id in expected:
            tier, spend = expected[pack.client.client_id]
            assert (pack.client.tier, pack.client.cumulative_spend_cny) == (tier, spend)
        assert pack.client.purchases_known


def test_birthday_loads_calendar_and_purchases_but_no_services_or_policies(data, cases):
    pack = prepare(by_id(cases)["C01"], data)
    facts = pack.facts_by_id()
    assert facts["calendar.birthday"].text == "客户生日：11月6日（今天）"
    assert {"p0001", "p0003", "p0007"} <= facts.keys()
    assert not kinds(pack) & {"service", "policy", "event"}


def test_owned_products_are_purchase_facts_not_specs(data, cases):
    pack = prepare(by_id(cases)["C04"], data)
    facts = pack.facts_by_id()
    assert "p0004" in facts  # the client's Colette
    assert not any(fid.startswith("colette.") for fid in facts)
    assert "sable.closure" in facts and "sv_usage_demo" in facts


def test_price_objection_loads_pricing_and_channels(data, cases):
    facts = prepare(by_id(cases)["C10"], data).facts_by_id()
    assert {"policy_pricing_1", "policy_channels_3", "margaux.price_cny"} <= facts.keys()
    assert not any(fid.startswith("policy_allocation") for fid in facts)  # no restricted product


def test_event_checks_eligibility_and_keeps_only_relevant_allocation_lines(data, cases):
    facts = prepare(by_id(cases)["C07"], data).facts_by_id()
    assert "在本活动参加范围内" in facts["ev_classic_details_2611.eligibility"].text
    assert "星期六" in facts["ev_classic_details_2611.time"].text
    allocation = [f.text for fid, f in facts.items() if fid.startswith("policy_allocation")]
    assert allocation and not any("Héritage" in t for t in allocation)


def test_reactivation_offers_only_events_the_client_can_attend(data, cases):
    core_client = prepare(by_id(cases)["C06"], data)
    assert "contact.last" in core_client.facts_by_id()
    assert "event" not in kinds(core_client)
    assert "margaux" in core_client.product_ids  # mentioned in history
    vic = by_id(cases)["C06"].model_copy(
        update={"client_information": ClientInformation(client_id="cl004")}
    )
    assert "ev_classic_details_2611.name" in prepare(vic, data).facts_by_id()


def test_generation_is_lenient_about_unknown_input(data, cases):
    case = by_id(cases)["C03"]
    odd = case.model_copy(
        update={
            "client_information": ClientInformation(name="周敏", salutation="周女士"),
            "product_information": ProductInformation(product_ids=["margaux", "birkin"]),
        }
    )
    pack = prepare(odd, data)
    assert pack.product_ids == ["margaux"]
    assert not pack.client.purchases_known and pack.client.tier is None
    assert any("birkin" in note for note in pack.notes)
    stranger = case.model_copy(update={"client_information": ClientInformation(client_id="cl999")})
    with pytest.raises(ValueError, match="no inline client information"):
        prepare(stranger, data)


def test_validate_data_rejects_inline_identity_that_disagrees(data, cases):
    case = by_id(cases)["C02"]
    wrong = ClientInformation(client_id="cl002", salutation="林小姐")
    with pytest.raises(ValueError, match="salutation disagrees"):
        data.foundation.check_case(case.model_copy(update={"client_information": wrong}))
