"""Repository for Account and Institution persistence."""

from __future__ import annotations

import uuid
from typing import Sequence

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import AccountModel, InstitutionModel
from app.domain.entities import Account, FinancialInstitution
from app.domain.errors import EntityNotFoundError

logger = structlog.get_logger(__name__)


class InstitutionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, institution: FinancialInstitution) -> InstitutionModel:
        """Return existing institution by type, or create if not found."""
        result = await self._session.execute(
            select(InstitutionModel).where(
                InstitutionModel.institution_type == institution.institution_type.value
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        model = InstitutionModel(
            id=str(institution.id),
            name=institution.name,
            institution_type=institution.institution_type.value,
            website=institution.website,
            created_at=institution.created_at,
        )
        self._session.add(model)
        await self._session.flush()
        logger.info("institution.created", name=model.name, type=model.institution_type)
        return model

    async def get_by_id(self, institution_id: uuid.UUID) -> InstitutionModel:
        result = await self._session.execute(
            select(InstitutionModel).where(InstitutionModel.id == str(institution_id))
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise EntityNotFoundError("Institution", institution_id)
        return model

    async def list_all(self) -> Sequence[InstitutionModel]:
        result = await self._session.execute(select(InstitutionModel))
        return result.scalars().all()


class AccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(
        self, account: Account, institution_id: str
    ) -> AccountModel:
        """Return existing account by masked number + institution, or create."""
        result = await self._session.execute(
            select(AccountModel).where(
                AccountModel.institution_id == institution_id,
                AccountModel.account_number_masked == account.account_number_masked,
            )
        )
        existing = result.scalar_one_or_none()
        if existing:
            return existing

        model = AccountModel(
            id=str(account.id),
            institution_id=institution_id,
            account_number_masked=account.account_number_masked,
            account_name=account.account_name,
            account_type=account.account_type.value,
            currency=account.currency,
            created_at=account.created_at,
        )
        self._session.add(model)
        await self._session.flush()
        logger.info(
            "account.created",
            account_id=model.id,
            masked=model.account_number_masked,
        )
        return model

    async def get_by_id(self, account_id: uuid.UUID) -> AccountModel:
        result = await self._session.execute(
            select(AccountModel).where(AccountModel.id == str(account_id))
        )
        model = result.scalar_one_or_none()
        if model is None:
            raise EntityNotFoundError("Account", account_id)
        return model

    async def list_by_institution(self, institution_id: str) -> Sequence[AccountModel]:
        result = await self._session.execute(
            select(AccountModel).where(AccountModel.institution_id == institution_id)
        )
        return result.scalars().all()
