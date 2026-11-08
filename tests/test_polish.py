from lacaze.application.polish import apply_rewrites, find_flags, rewrite_problems
from lacaze.application.preparation import prepare
from lacaze.application.workflow import AdvisorWorkflow
from lacaze.domain.plan import Draft, Flag, Rewrite
from tests.conftest import ScriptedModel


def draft(text, angle=1):
    return Draft(angle=angle, text=text, fact_ids=[])


def test_flags_both_habits_sentence_by_sentence(data):
    text = (
        "林女士，Colette 是小羊皮，怕刮。至于会不会变形，我这边没有可以给您的说法，就不乱说了。"
        "您方便的时候告诉我，不着急。"
    )
    flags = find_flags([draft(text)], data.polish)
    assert [(f.sentence, f.kinds) for f in flags] == [
        ("至于会不会变形，我这边没有可以给您的说法，就不乱说了。", ["defensive"]),
        ("您方便的时候告诉我，不着急。", ["reassurance"]),
    ]


def test_ordinary_sentences_are_not_flagged(data):
    ordinary = [
        "陈先生，抱歉这几天才回复您。",
        "用久了光泽会慢慢有变化，这是正常的，您看到不必担心。",
        "价格全国门店统一，没有首购折扣。",
        "这次的私览暂时没法为您安排，很抱歉。",
        "有问题可以直接微信问我。",
    ]
    assert find_flags([draft(t) for t in ordinary[:3]], data.polish) == []
    assert find_flags([draft(" ".join(ordinary[3:]))], data.polish) == []


def test_only_the_rewritten_sentence_changes():
    text = "林女士，这只能放 13 寸电脑。不用特意回复。有问题随时找我。"
    flag = Flag(angle=1, sentence="不用特意回复。", kinds=["reassurance"])
    (new,), edits = apply_rewrites(
        [draft(text)], [Rewrite(angle=1, sentence=flag.sentence, replacement="")], [flag]
    )
    assert new.text == "林女士，这只能放 13 寸电脑。有问题随时找我。"
    assert [(e.before, e.after) for e in edits] == [("不用特意回复。", "")]
    unchanged = Rewrite(angle=1, sentence=flag.sentence, replacement=flag.sentence)
    (same,), none = apply_rewrites([draft(text)], [unchanged], [flag])
    assert same.text == text and none == []


def test_rewrites_that_add_or_lose_content_are_rejected(data, cases):
    pack = prepare(cases[1], data)  # 林女士
    sentence = "林女士，尺寸我这边没有数据，就不乱说了。"
    flags = [Flag(angle=1, sentence=sentence, kinds=["defensive"])]

    def problems(replacement, sentence=sentence):
        rewrite = Rewrite(angle=1, sentence=sentence, replacement=replacement)
        return rewrite_problems(rewrite, flags, pack, data)

    assert problems("林女士，尺寸要看实物才说得准。") == []
    assert problems(sentence) == []  # kept as is
    assert problems("尺寸要看实物。")  # salutation lost
    assert problems("林女士，Odette 要看实物。")  # new product
    assert problems("林女士，这只 8.5 万元。")  # new price
    assert problems("林女士，不乱说了。")  # still defensive
    assert problems("林女士，尺寸要看实物才说得准，到店我带您仔细比一比好吗。")  # longer
    assert problems("林女士。", sentence="另一句。")  # not a flagged sentence


async def test_workflow_polishes_flagged_sentences_only(data, cases):
    result = await AdvisorWorkflow(ScriptedModel().model, data).generate(cases[1])
    third = result.candidates.messages[2]
    assert third == "林女士，先留个余地。"
    assert [(e.angle, e.before, e.after) for e in result.edits] == [
        (3, "您可以按自己的节奏慢慢看。", "")
    ]
    assert result.drafts[2].text == third and not result.warnings


async def test_bad_rewrite_is_retried_then_original_kept(data, cases):
    once = ScriptedModel(polish_fault="made_up_price")
    result = await AdvisorWorkflow(once.model, data).generate(cases[1])
    assert result.usage[2].requests == 2 and result.candidates.messages[2] == "林女士，先留个余地。"
    always = ScriptedModel(polish_fault="made_up_price", persistent=True)
    result = await AdvisorWorkflow(always.model, data).generate(cases[1])
    assert "节奏" in result.candidates.messages[2] and "七万五" not in result.candidates.messages[2]
    assert result.edits == [] and any("修整" in w for w in result.warnings)


async def test_repolish_applies_the_stage_to_an_earlier_result(data, cases):
    flow = AdvisorWorkflow(ScriptedModel().model, data)
    result = await flow.generate(cases[1])
    earlier = result.model_copy(
        update={
            "drafts": [d.model_copy(update={"text": d.text + "不着急。"}) for d in result.drafts]
        }
    )
    again = await flow.repolish(earlier)
    assert again.candidates.messages == result.candidates.messages
    assert len(again.edits) == 3 and len(again.usage) == len(result.usage) + 1
    assert again.pack == result.pack and again.plan == result.plan
