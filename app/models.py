from datetime import date, datetime
from sqlalchemy import String, Integer, Float, Date, DateTime, ForeignKey, CheckConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint("age >= 0 AND age <= 130", name="ck_customers_age_range"),
    )

    customer_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    # Indexed: GET /claims?city= filters on this directly.
    city: Mapped[str] = mapped_column(String, nullable=False, index=True)
    state: Mapped[str] = mapped_column(String, nullable=False)

    policies: Mapped[list["Policy"]] = relationship(back_populates="customer")


class Policy(Base):
    __tablename__ = "policies"
    __table_args__ = (
        CheckConstraint("coverage_limit > 0", name="ck_policies_coverage_limit_positive"),
        CheckConstraint("deductible >= 0", name="ck_policies_deductible_non_negative"),
    )

    policy_id: Mapped[str] = mapped_column(String, primary_key=True)
    # Indexed: every claims upload and every claims join filters/looks up by
    # this FK. SQLite does not automatically index foreign key columns
    # (unlike Postgres/MySQL, which also don't always -- this is a common
    # blind spot regardless of database), so without index=True here every
    # claims-to-policy join is a full table scan on this column.
    customer_id: Mapped[str] = mapped_column(
        String, ForeignKey("customers.customer_id"), nullable=False, index=True
    )
    policy_issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    coverage_limit: Mapped[float] = mapped_column(Float, nullable=False)
    deductible: Mapped[float] = mapped_column(Float, nullable=False)
    # Indexed: GET /claims?state=, GET /reports/state, and the CA-flood
    # payout rule all filter or group on this column directly.
    state: Mapped[str] = mapped_column(String, nullable=False, index=True)

    customer: Mapped["Customer"] = relationship(back_populates="policies")
    claims: Mapped[list["Claim"]] = relationship(back_populates="policy")


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        CheckConstraint("loss_amount >= 0", name="ck_claims_loss_amount_non_negative"),
        CheckConstraint("final_payout >= 0", name="ck_claims_final_payout_non_negative"),
    )

    claim_id: Mapped[str] = mapped_column(String, primary_key=True)
    # Indexed: same FK-join reasoning as Policy.customer_id above -- every
    # claim lookup by policy (and every upload's duplicate/orphan check)
    # filters on this.
    policy_id: Mapped[str] = mapped_column(
        String, ForeignKey("policies.policy_id"), nullable=False, index=True
    )
    # Indexed: default sort column on GET /claims and a common filter
    # (date_from / date_to).
    loss_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    loss_amount: Mapped[float] = mapped_column(Float, nullable=False)
    # Indexed: sortable/filterable via GET /claims?cause=.
    cause: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # Indexed: sortable via GET /claims?sort_by=final_payout and filterable
    # via min_payout/max_payout.
    final_payout: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    policy: Mapped["Policy"] = relationship(back_populates="claims")
