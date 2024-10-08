from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from dscommerce_fastapi.database import get_session
from dscommerce_fastapi.db.models.categories import Category
from dscommerce_fastapi.db.models.products import Product
from dscommerce_fastapi.db.models.users import User
from dscommerce_fastapi.schemas import Message
from dscommerce_fastapi.security import get_current_user

router = APIRouter(prefix='/products', tags=['products'])

T_Session = Annotated['Session', Depends(get_session)]
T_CurrentUser = Annotated[User, Depends(get_current_user)]


# receber
class ProductCreate(BaseModel):
    name: str
    serial_code: str
    description: str | None = None
    price: float
    img_url: str
    category_id: int


class CategoryRead(BaseModel):
    id: int
    name: str

    # acho que não precisa, testar depois
    model_config = ConfigDict(from_attributes=True)


# retornar
class ProductRead(BaseModel):
    id: int
    name: str
    serial_code: str
    description: str | None = None
    price: float
    img_url: str
    category: CategoryRead

    model_config = ConfigDict(from_attributes=True)


class ListProductRead(BaseModel):
    products: list[ProductRead]


@router.post('', status_code=HTTPStatus.CREATED, response_model=ProductRead)
def create_product(
    data: ProductCreate, db: T_Session, current_user: T_CurrentUser
):
    query = select(Product).where(Product.serial_code == data.serial_code)

    db_product = db.scalar(query)

    if db_product:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST, detail='Product already exists'
        )

    category = db.scalar(
        select(Category).where(Category.id == data.category_id)
    )
    if not category:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Category not found'
        )

    db_product = Product(**data.model_dump(exclude_unset=True))

    db_product.created_by = current_user

    db.add(db_product)
    db.commit()
    db.refresh(db_product)

    return db_product


@router.get('', status_code=HTTPStatus.OK, response_model=ListProductRead)
def read_products(  # noqa
    db: T_Session,
    name: str | None = None,
    serial_code: str | None = None,
    price: float | None = None,
    description: str | None = None,
    limit: int = 10,
    offset: int = 0,
):
    # só de category estar no formato certo no ProductRead,
    # basta o join que ele retorne tudo certinho
    query = (
        select(Product)
        .join(Category)
        .limit(limit)
        .offset(offset)
        .where(Product.is_active, Product.category_id == Category.id)
    )

    if name:
        query = query.where(Product.name.contains(name))

    if serial_code:
        query = query.filter(Product.serial_code.contains(serial_code))

    if price:
        query = query.where(Product.price == price)

    if description:
        # poderia ser f'{description}%' ou f'%{description}' também poderia ser
        # query = query.filter(Product.description.like(f'%{description}%'))
        query = query.where(Product.description.like(f'%{description}%'))

    db_products = db.scalars(query).all()

    return {'products': db_products}


class ProductUpdate(BaseModel):
    name: str | None = None
    serial_code: str | None = None
    description: str | None = None
    price: float | None = None
    img_url: str | None = None
    category_id: int | None = None


@router.patch(
    '/{product_id}', status_code=HTTPStatus.OK, response_model=ProductRead
)
def update_product(
    product_id: int,
    data: ProductUpdate,
    db: T_Session,
    current_user: T_CurrentUser,
):
    query = select(Product).where(
        Product.id == product_id,
        Product.is_active,
        Product.created_by_id == current_user.id,
    )

    db_product = db.scalar(query)

    if not db_product:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Product not found'
        )

    if data.category_id:
        category = db.scalar(
            select(Category).where(Category.id == data.category_id)
        )
        if not category:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND, detail='Category not found'
            )

    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(db_product, key, value)

    db_product.updated_by = current_user

    db.add(db_product)
    db.commit()
    db.refresh(db_product)

    return db_product


@router.delete(
    '/{product_id}', status_code=HTTPStatus.OK, response_model=Message
)
def delete_product(
    product_id: int, db: T_Session, current_user: T_CurrentUser
):
    query = select(Product).where(
        Product.id == product_id,
        Product.is_active,
        Product.created_by_id == current_user.id,
    )

    db_product = db.scalar(query)

    if not db_product:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail='Product not found'
        )

    db_product.is_active = False
    db.commit()
    db.refresh(db_product)

    return {'message': 'Product deleted successfully'}
