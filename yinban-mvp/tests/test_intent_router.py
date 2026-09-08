from app.core.data_loader import load_json
from app.core.dialogue_engine import DialogueEngine
from app.core.intent_router import IntentRouter


def build_router() -> IntentRouter:
    return IntentRouter(load_json("hospital.json"), load_json("intents.json"))


def test_demo_phrases_are_classified() -> None:
    router = build_router()
    cases = [
        ("我要去心内科", "navigate", "cardiology"),
        ("心脏科怎么走", "navigate", "cardiology"),
        ("我挂了心血管内科", "navigate", "cardiology"),
        ("我要取药", "navigate", "pharmacy"),
        ("药房在哪里", "navigate", "pharmacy"),
        ("厕所在哪儿", "navigate", "toilet"),
        ("我想找洗手间", "navigate", "toilet"),
        ("我要去抽血", "navigate", "laboratory"),
        ("挂号处在哪里", "navigate", "registration"),
        ("我下一步该干什么", "process", "next_step"),
        ("我不会挂号", "process", "registration"),
        ("在哪里缴费", "process", "payment"),
        ("我不舒服", "help", None),
        ("帮我找工作人员", "help", None),
        ("请停下", "stop", None),
    ]
    for text, intent, destination in cases:
        result = router.match(text)
        assert result.intent == intent, text
        assert result.destination == destination, text


def test_stop_has_priority() -> None:
    result = build_router().match("停下，我不去心内科了")
    assert result.intent == "stop"


def test_multiple_destinations_are_kept_in_spoken_order() -> None:
    result = build_router().match("我先去药房，再去检验科")
    assert result.intent == "navigate"
    assert result.destination == "pharmacy"
    assert result.destinations == ("pharmacy", "laboratory")


def test_multiple_destinations_take_priority_over_generic_process_phrase() -> None:
    result = build_router().match("我先去药房，再去检验科，应该怎么办")
    assert result.intent == "navigate"
    assert result.destinations == ("pharmacy", "laboratory")


def test_empty_and_unknown_input() -> None:
    router = build_router()
    assert router.match("   ").intent == "unknown"
    assert router.match("今天天气怎么样").intent == "unknown"


def test_medical_question_gets_safety_reply() -> None:
    hospital = load_json("hospital.json")
    router = IntentRouter(hospital, load_json("intents.json"))
    engine = DialogueEngine(hospital)
    text = "我应该吃什么药"
    reply = engine.reply(text, router.match(text))
    assert "不能" in reply
    assert "医护人员" in reply


def test_multiple_destination_reply_answers_every_stop() -> None:
    hospital = load_json("hospital.json")
    router = IntentRouter(hospital, load_json("intents.json"))
    engine = DialogueEngine(hospital)
    text = "我先去药房，再去检验科"
    reply = engine.reply(text, router.match(text))
    assert "第一站" in reply
    assert "药房，位于" in reply
    assert "第二站" in reply
    assert "检验科，位于" in reply
    assert reply.index("药房") < reply.index("检验科")
