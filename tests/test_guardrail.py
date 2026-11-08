from lacaze.application.guardrail import draft_problems, soft_warnings
from lacaze.application.preparation import prepare
from lacaze.application.workflow import AdvisorWorkflow
from lacaze.domain.plan import Angle, Draft, Drafts, Plan
from tests.conftest import ScriptedModel


def plan_with(fact_ids):
    angle = {"point": "回应", "purpose": "回应", "message_ids": ["m001"], "next_step": None}
    return Plan(
        situation="客户在比较",
        sub_type="比较候选",
        avoid=[],
        fact_ids=fact_ids,
        angles=[Angle(name=f"角度{i}", **angle) for i in range(1, 4)],
        missing=[],
    )


def drafts(*texts):
    return Drafts(drafts=[Draft(angle=i, text=t, fact_ids=[]) for i, t in enumerate(texts, 1)])


def problems_for(text, data, case, fact_ids=()):
    pack = prepare(case, data)
    filler = ["林女士，您先看看。", "林女士，不着急，慢慢比较。"]
    return draft_problems(drafts(text, *filler), pack, plan_with(list(fact_ids)), data)


def test_true_facts_pass(data, cases):
    ok = "林女士，Odette 是 8.5 万元，13 英寸笔记本电脑能放进去；您现在背的 Sablé 日常继续用就好。"
    assert problems_for(ok, data, cases[1]) == []


def test_made_up_price_date_and_time_are_problems(data, cases):
    found = problems_for("林女士，Odette 现在七万五，12月3日15:00可以来看。", data, cases[1])
    assert any("价格" in p for p in found)
    assert any("日期" in p for p in found)
    assert any("时间" in p for p in found)


def test_out_of_scope_product_and_internal_information_are_problems(data, cases):
    found = problems_for(
        "林女士，您是 VIC 客户，Héritage 也可以考虑（见 sv_monogram）。", data, cases[1]
    )
    assert any("Héritage" in p for p in found)
    assert any("VIC" in p and "sv_monogram" in p for p in found)


def test_missing_salutation_and_length_are_problems(data, cases):
    found = problems_for("您好，" + "很" * 210, data, cases[1])
    assert any("称呼" in p for p in found) and any("压缩" in p for p in found)


def test_owned_and_event_products_are_in_scope(data, cases):
    # C07: the client owns Odette; Véronique is featured at the event.
    text = "张女士，您那只海军蓝的 Odette 用得还好吗？这次私览会介绍 Véronique。"
    pack = prepare(cases[6], data)
    filler = ["张女士，您先看看。", "张女士，不着急。"]
    assert draft_problems(drafts(text, *filler), pack, plan_with([]), data) == []


def test_soft_warnings_do_not_block(data, cases):
    pack = prepare(cases[1], data)
    same = "林女士，Odette 的分隔比较多，文件和小物可以分开放。"
    warnings = soft_warnings(
        drafts(same + "！", same + "呢", "林女士，Odette 不打折。"), pack, data
    )
    assert any("感叹号" in w for w in warnings)
    assert any("相似" in w for w in warnings)
    assert any("打折" in w and "本场景" in w for w in warnings)


async def test_made_up_price_is_retried_then_reported_if_it_persists(data, cases):
    once = await AdvisorWorkflow(ScriptedModel(draft_fault="made_up_price").model, data).generate(
        cases[1]
    )
    assert once.usage[1].requests == 2 and not once.warnings
    always = ScriptedModel(draft_fault="made_up_price", persistent=True)
    result = await AdvisorWorkflow(always.model, data).generate(cases[1])
    assert "七万五" in result.candidates.messages[1]  # returned for the CA to see, not dropped
    assert any("价格" in w for w in result.warnings)


def test_plan_citing_too_many_facts_is_a_problem(data, cases):
    from lacaze.application.plan_checks import plan_problems

    pack = prepare(cases[1], data)
    many = [f.fact_id for f in pack.facts if not f.internal][: data.guardrail.max_plan_facts + 1]
    plan = plan_with(many)
    plan = plan.model_copy(
        update={
            "angles": [
                a.model_copy(update={"message_ids": [f"m00{i}"]})
                for i, a in enumerate(plan.angles, 1)
            ]
        }
    )
    problems = plan_problems(plan, pack, data)
    assert len([p for p in problems if "最多" in p]) == 1


def test_angle_must_rest_on_this_clients_words_or_purchases(data, cases):
    from lacaze.application.plan_checks import plan_problems

    pack = prepare(cases[1], data)
    plan = plan_with(["sv_private_viewing"])
    generic = plan.angles[0].model_copy(update={"message_ids": []})
    plan = plan.model_copy(update={"angles": [generic, *plan.angles[1:]]})
    problems = plan_problems(plan, pack, data)
    assert any(p.startswith("角度 1 没有落在这位客户身上") for p in problems)
    # Her purchase among the shared facts grounds every angle.
    owned = plan.model_copy(update={"fact_ids": ["sv_private_viewing", "p0006"]})
    assert not any("没有落在" in p for p in plan_problems(owned, pack, data))


def test_internal_fact_in_an_angle_is_a_problem(data, cases):
    from lacaze.application.plan_checks import plan_problems

    pack = prepare(cases[6], data)
    plan = plan_with(["ev_classic_details_2611.not_included"])
    assert any("内部事实" in p for p in plan_problems(plan, pack, data))


def test_english_leaking_into_chinese_is_a_problem(data, cases):
    found = problems_for("林女士，谢谢您仍然 considering Odette。", data, cases[1])
    assert any("considering" in p for p in found)
    assert not any("Odette" in p for p in found)  # product names from the facts are fine


def test_service_is_split_into_what_and_how(data, cases):
    facts = prepare(cases[3], data).facts_by_id()
    assert "约 7 天" not in facts["sv_annual_care"].text
    assert "约 7 天" in facts["sv_annual_care.how"].text


def test_any_draft_may_use_any_planned_fact(data, cases):
    """The three drafts are alternatives for one request, so planned facts are shared."""
    pack = prepare(cases[1], data)
    plan = plan_with(["odette.interior", "margaux.interior"])
    texts = ["林女士，两款的分隔我整理好了。", "林女士，先说 Margaux。", "林女士，再说 Odette。"]
    shared = Drafts(
        drafts=[
            Draft(angle=i, text=t, fact_ids=["odette.interior", "margaux.interior"])
            for i, t in enumerate(texts, 1)
        ]
    )
    assert not [p for p in draft_problems(shared, pack, plan, data) if "计划之外" in p]
    outside = shared.model_copy(
        update={
            "drafts": [shared.drafts[0].model_copy(update={"fact_ids": ["sable.weight_g"]})]
            + shared.drafts[1:]
        }
    )
    assert any("计划之外" in p for p in draft_problems(outside, pack, plan, data))
