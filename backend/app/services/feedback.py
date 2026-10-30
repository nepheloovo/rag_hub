"""回答反馈：数据库原子 upsert，避免并发提交产生重复评分。"""
import uuid

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.chat import Message, MessageFeedback


def save_feedback(db: Session, message_id: str, user_id: str, rating: int, comment: str | None):
    message = db.get(Message, message_id)
    if not message:
        raise HTTPException(status_code=404, detail="回答不存在")
    if message.role != "assistant":
        raise HTTPException(status_code=422, detail="只能对助手回答反馈")
    if rating == 0:
        db.query(MessageFeedback).filter(
            MessageFeedback.message_id == message_id, MessageFeedback.user_id == user_id
        ).delete(synchronize_session=False)
    else:
        statement = insert(MessageFeedback).values(
            id=uuid.uuid4().hex,
            message_id=message_id,
            user_id=user_id,
            rating=rating,
            comment=comment or "",
        )
        db.execute(statement.on_conflict_do_update(
            constraint="uq_message_feedback_user",
            set_={"rating": rating, "comment": comment or "", "updated_at": func.now()},
        ))
    db.commit()
    return {"ok": True, "rating": rating}


def message_dicts(db: Session, messages: list[Message], user_id: str) -> list[dict]:
    """批量补充当前用户的评分，不在 ORM 对象上写临时属性。"""
    ids = [message.id for message in messages if message.role == "assistant"]
    ratings = dict(db.query(MessageFeedback.message_id, MessageFeedback.rating).filter(
        MessageFeedback.message_id.in_(ids), MessageFeedback.user_id == user_id
    ).all()) if ids else {}
    result = []
    for message in messages:
        row = {
            "id": message.id,
            "conv_id": message.conv_id,
            "role": message.role,
            "content": message.content,
            "refs": message.refs or [],
            "created_at": message.created_at,
        }
        if message.role == "assistant":
            row["feedback"] = ratings.get(message.id, 0)
        result.append(row)
    return result
