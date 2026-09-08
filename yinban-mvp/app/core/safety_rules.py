from __future__ import annotations


MEDICAL_REQUEST_KEYWORDS = (
    "诊断",
    "什么病",
    "吃什么药",
    "用药",
    "剂量",
    "处方",
    "治疗",
)


def is_medical_request(text: str) -> bool:
    return any(keyword in text for keyword in MEDICAL_REQUEST_KEYWORDS)


def unknown_reply(text: str) -> str:
    if is_medical_request(text):
        return (
            "我只能提供院内导引和就医流程信息，不能进行诊断或提供用药建议。"
            "请咨询现场医护人员。"
        )
    return "抱歉，我还没有听懂。您可以说“我要去心内科”，或点击下方的大按钮。"

