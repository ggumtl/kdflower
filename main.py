import os
import uuid
from io import BytesIO
from PIL import Image, ImageOps

from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi import FastAPI, Depends, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session

import models
from database import engine, get_db

# DB 테이블 자동 생성
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# 세션 미들웨어 설정 (하드코딩 로그인 상태 저장용)
app.add_middleware(SessionMiddleware, secret_key="admin-secret-key-change-this")

# 디렉터리 생성 및 정적/템플릿 연결
os.makedirs("static/uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# -------------------------------------------------------------------
# 사용자 화면 (index.html)
# -------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def read_root(request: Request, db: Session = Depends(get_db)):
    # order_no 순으로 카테고리 정렬
    categories = db.query(models.Category).order_by(models.Category.order_no.asc(), models.Category.idx.asc()).all()
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"categories": categories}
    )


# -------------------------------------------------------------------
# /admin 인증 및 메뉴 라우트
# -------------------------------------------------------------------

# 1. 로그인 화면 GET / POST
@app.get("/admin/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(
        request=request, 
        name="admin/login.html"
    )

@app.post("/admin/login")
def login_action(
    request: Request,
    username: str = Form(...),
    password: str = Form(...)
):
    if username == "admin" and password == "admin":
        request.session["is_admin"] = True
        return RedirectResponse(url="/admin/flower", status_code=303)
    
    return templates.TemplateResponse(
        request=request,
        name="admin/login.html", 
        context={"error": "아이디 또는 비밀번호가 올바르지 않습니다."}
    )

# 로그아웃
@app.get("/admin/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/admin/login", status_code=303)


# 2. 카테고리 관리 GET / POST
@app.get("/admin/category", response_class=HTMLResponse)
def category_page(request: Request, db: Session = Depends(get_db)):
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin/login", status_code=303)
        
    categories = db.query(models.Category).order_by(models.Category.order_no.asc(), models.Category.idx.asc()).all()
    return templates.TemplateResponse(
        request=request,
        name="admin/category.html", 
        context={"categories": categories}
    )

@app.post("/admin/category")
def create_category(
    request: Request,
    name: str = Form(...),
    order_no: int = Form(0),
    db: Session = Depends(get_db)
):
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin/login", status_code=303)

    new_cat = models.Category(name=name, order_no=order_no)
    db.add(new_cat)
    db.commit()
    return RedirectResponse(url="/admin/category", status_code=303)

@app.post("/admin/category/edit/{cat_id}")
def update_category(
    cat_id: int,
    request: Request,
    name: str = Form(...),
    order_no: int = Form(0),
    db: Session = Depends(get_db)
):
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin/login", status_code=303)

    cat = db.query(models.Category).filter(models.Category.idx == cat_id).first()
    if cat:
        cat.name = name
        cat.order_no = order_no
        db.commit()

    return RedirectResponse(url="/admin/category", status_code=303)


# 3. 꽃 목록 & 등록 GET / POST
@app.get("/admin/flower", response_class=HTMLResponse)
def flower_page(
    request: Request, 
    category_id: int = None,
    db: Session = Depends(get_db)
):
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin/login", status_code=303)

    categories = db.query(models.Category).order_by(models.Category.order_no.asc(), models.Category.idx.asc()).all()
    
    query = db.query(models.FlowerList)
    if category_id:
        query = query.filter(models.FlowerList.category == category_id)
        
    # 이름순(가나다순) 오름차순 정렬
    flowers = query.order_by(models.FlowerList.name.asc()).all()
    
    return templates.TemplateResponse(
        request=request,
        name="admin/flower_list.html",
        context={
            "categories": categories, 
            "flowers": flowers,
            "selected_category": category_id
        }
    )

@app.post("/admin/flower")
async def create_flower(
    request: Request,
    name: str = Form(...),
    name2: str = Form(None),
    color: str = Form(None),
    price: int = Form(0),
    category_idx: str = Form(...),
    file: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin/login", status_code=303)

    img_path = None

    if file and file.filename:
        filename_ext = os.path.splitext(file.filename)[1]
        unique_filename = f"flower_{uuid.uuid4().hex[:8]}{filename_ext}"
        save_rel_path = os.path.join("static", "uploads", unique_filename)
        
        contents = await file.read()
        image = Image.open(BytesIO(contents))
        
        # EXIF 방향 정보 감지 및 회전 보정
        image = ImageOps.exif_transpose(image)
        
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")
            
        image.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
        image.save(save_rel_path, quality=90)

        img_path = save_rel_path.replace("\\", "/")

    cat_id = int(category_idx) if category_idx and category_idx.isdigit() else None

    new_flower = models.FlowerList(
        name=name,
        name2=name2,
        color=color,
        price=price,
        category=cat_id,
        img_path=img_path
    )
    db.add(new_flower)
    db.commit()

    return RedirectResponse(url="/admin/flower", status_code=303)


# 4. 관리자 갤러리 뷰 GET
@app.get("/admin/gallery-view", response_class=HTMLResponse)
def gallery_view_page(request: Request, db: Session = Depends(get_db)):
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin/login", status_code=303)

    categories = db.query(models.Category).order_by(models.Category.order_no.asc(), models.Category.idx.asc()).all()
    return templates.TemplateResponse(
        request=request,
        name="admin/gallery_view.html",
        context={"categories": categories}
    )


@app.post("/admin/flower/edit/{flower_id}")
async def update_flower(
    flower_id: int,
    request: Request,
    name: str = Form(...),
    name2: str = Form(None),
    color: str = Form(None),
    price: int = Form(0),
    category_idx: str = Form(...),
    file: UploadFile = File(None),
    redirect_to: str = "/admin/flower",  # 리다이렉트 경로 파라미터 추가
    db: Session = Depends(get_db)
):
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin/login", status_code=303)

    flower = db.query(models.FlowerList).filter(models.FlowerList.idx == flower_id).first()
    if not flower:
        return RedirectResponse(url=redirect_to, status_code=303)

    flower.name = name
    flower.name2 = name2
    flower.color = color
    flower.price = price
    flower.category = int(category_idx)

    if file and file.filename:
        filename_ext = os.path.splitext(file.filename)[1]
        unique_filename = f"flower_{uuid.uuid4().hex[:8]}{filename_ext}"
        save_rel_path = os.path.join("static", "uploads", unique_filename)

        contents = await file.read()
        image = Image.open(BytesIO(contents))
        
        # EXIF 방향 정보 감지 및 회전 보정
        image = ImageOps.exif_transpose(image)
        
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")
            
        image.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
        image.save(save_rel_path, quality=90)

        if flower.img_path and os.path.exists(flower.img_path):
            try:
                os.remove(flower.img_path)
            except OSError:
                pass

        flower.img_path = save_rel_path.replace("\\", "/")

    db.commit()
    # 요청 받은 redirect_to 경로로 리다이렉트
    return RedirectResponse(url=redirect_to, status_code=303)

# 6. 꽃 삭제 POST
@app.post("/admin/flower/delete/{flower_id}")
def delete_flower(
    flower_id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin/login", status_code=303)

    flower = db.query(models.FlowerList).filter(models.FlowerList.idx == flower_id).first()
    if flower:
        if flower.img_path and os.path.exists(flower.img_path):
            try:
                os.remove(flower.img_path)
            except OSError:
                pass
                
        db.delete(flower)
        db.commit()

    return RedirectResponse(url="/admin/flower", status_code=303)


# 7. 노출 상태(View 1/0) 토글 POST
@app.post("/admin/flower/toggle-view/{flower_id}")
def toggle_flower_view(
    flower_id: int,
    request: Request,
    redirect_to: str = "/admin/flower",
    db: Session = Depends(get_db)
):
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin/login", status_code=303)

    flower = db.query(models.FlowerList).filter(models.FlowerList.idx == flower_id).first()
    if flower:
        flower.view = 0 if flower.view == 1 else 1
        db.commit()

    return RedirectResponse(url=redirect_to, status_code=303)

# DB 백업 파일 다운로드 라우트 추가
@app.get("/admin/db-backup")
def db_backup(request: Request):
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/admin/login", status_code=303)

    db_path = "flower.db"
    
    # DB 파일 존재 여부 확인 후 다운로드 응답
    if os.path.exists(db_path):
        return FileResponse(
            path=db_path,
            filename="flower_backup.db",
            media_type="application/octet-stream"
        )
    else:
        return RedirectResponse(url="/admin/flower", status_code=303)
    