from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import ValidationError
from app import models, schemas, crud, utils
from app.database import get_db
from sqlalchemy.ext.asyncio import AsyncSession
from app.config import settings
from typing import Annotated

router = APIRouter()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: AsyncSession = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = schemas.TokenData(username=username)
    except (JWTError, ValidationError):
        raise credentials_exception
    user = await crud.get_user_by_username(db, username=token_data.username)
    if user is None:
        raise credentials_exception
    return user

@router.post("/", response_model=schemas.User)
async def create_user(user: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    db_user = await crud.get_user_by_email(db, user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    db_user = await crud.get_user_by_username(db, user.username)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    hashed_password = utils.get_password_hash(user.password)
    user_in_db = models.UserORM(username=user.username, email=user.email, full_name=user.full_name, hashed_password=hashed_password)
    db.add(user_in_db)
    await db.commit()
    await db.refresh(user_in_db)
    return schemas.User(id=user_in_db.id, username=user_in_db.username, email=user_in_db.email, full_name=user_in_db.full_name, is_active=user_in_db.is_active)

@router.get("/me", response_model=schemas.User)
async def read_users_me(current_user: models.UserORM = Depends(get_current_user)):
    return current_user
