from extensions import db
from utils.time import utc_now_naive


class PlanPricing(db.Model):
    __tablename__ = 'plan_pricing'
    __table_args__ = (
        db.UniqueConstraint('plan_key', name='uq_plan_pricing_plan_key'),
    )

    id = db.Column(db.Integer, primary_key=True)
    plan_key = db.Column(db.String(32), nullable=False, index=True)
    price_label = db.Column(db.String(120), nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive, onupdate=utc_now_naive)

    def __repr__(self):
        return f'<PlanPricing {self.plan_key}:{self.price_label}>'
