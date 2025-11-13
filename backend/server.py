from fastapi import FastAPI, APIRouter, HTTPException, status
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, EmailStr
from typing import List, Optional
import uuid
from datetime import datetime, timezone
from passlib.context import CryptContext
import jwt
from jwt import PyJWTError

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production')
ALGORITHM = "HS256"

# Create the main app
app = FastAPI()
api_router = APIRouter(prefix="/api")

# ============ MODELS ============

class UserRegister(BaseModel):
    name: str
    email: EmailStr
    password: str
    user_type: str = "customer"  # customer, admin, delivery_person

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    email: str
    user_type: str
    phone: Optional[str] = None
    address: Optional[str] = None
    is_available: bool = True  # for delivery persons

class FoodItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    name: str
    category: str
    price: float
    image: str
    description: str
    restaurant: str
    available: bool = True

class CartItem(BaseModel):
    id: str
    name: str
    price: float
    quantity: int
    image: str

class Coupon(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    code: str
    discount_type: str  # percentage or fixed
    discount_value: float
    min_order_value: float
    max_discount: Optional[float] = None
    valid_until: str
    active: bool = True

class CouponCreate(BaseModel):
    code: str
    discount_type: str
    discount_value: float
    min_order_value: float
    max_discount: Optional[float] = None
    valid_until: str

class CouponValidate(BaseModel):
    code: str
    order_total: float

class OrderCreate(BaseModel):
    items: List[CartItem]
    total: float
    payment_method: str
    delivery_address: str
    coupon_code: Optional[str] = None
    discount_amount: float = 0

class Order(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    customer_id: str
    customer_name: str
    items: List[dict]
    total: float
    payment_method: str
    delivery_address: str
    coupon_code: Optional[str] = None
    discount_amount: float = 0
    status: str = "Placed"
    delivery_person_id: Optional[str] = None
    delivery_person_name: Optional[str] = None
    timestamp: str
    rating: Optional[int] = None
    review: Optional[str] = None

class OrderStatusUpdate(BaseModel):
    status: str

class DeliveryAssignment(BaseModel):
    delivery_person_id: str

class OrderReview(BaseModel):
    rating: int
    review: str

# ============ HELPER FUNCTIONS ============

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_token(user_id: str, email: str, user_type: str) -> str:
    payload = {"user_id": user_id, "email": email, "user_type": user_type}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ============ SEED DATA ============

async def seed_data():
    # Check if food items exist
    count = await db.food_items.count_documents({})
    if count == 0:
        food_items = [
            {"id": str(uuid.uuid4()), "name": "Margherita Pizza", "category": "Pizza", "price": 12.99, "image": "https://images.unsplash.com/photo-1604068549290-dea0e4a305ca?w=400&h=300&fit=crop", "description": "Classic tomato and mozzarella", "restaurant": "Italian Corner", "available": True},
            {"id": str(uuid.uuid4()), "name": "Chicken Burger", "category": "Burgers", "price": 9.99, "image": "https://images.unsplash.com/photo-1586190848861-99aa4a171e90?w=400&h=300&fit=crop", "description": "Grilled chicken with lettuce", "restaurant": "Burger Palace", "available": True},
            {"id": str(uuid.uuid4()), "name": "Caesar Salad", "category": "Salads", "price": 7.99, "image": "https://images.unsplash.com/photo-1550304943-4f24f54ddde9?w=400&h=300&fit=crop", "description": "Fresh romaine with parmesan", "restaurant": "Green Bowl", "available": True},
            {"id": str(uuid.uuid4()), "name": "Pepperoni Pizza", "category": "Pizza", "price": 14.99, "image": "https://images.unsplash.com/photo-1628840042765-356cda07504e?w=400&h=300&fit=crop", "description": "Loaded with pepperoni", "restaurant": "Italian Corner", "available": True},
            {"id": str(uuid.uuid4()), "name": "Veggie Burger", "category": "Burgers", "price": 8.99, "image": "https://images.unsplash.com/photo-1525059696034-4967a729002a?w=400&h=300&fit=crop", "description": "Plant-based patty", "restaurant": "Burger Palace", "available": True},
            {"id": str(uuid.uuid4()), "name": "Greek Salad", "category": "Salads", "price": 8.99, "image": "https://images.unsplash.com/photo-1540189549336-e6e99c3679fe?w=400&h=300&fit=crop", "description": "Feta, olives, and cucumbers", "restaurant": "Green Bowl", "available": True},
            {"id": str(uuid.uuid4()), "name": "Pad Thai", "category": "Asian", "price": 11.99, "image": "https://images.unsplash.com/photo-1559314809-0d155014e29e?w=400&h=300&fit=crop", "description": "Traditional Thai noodles", "restaurant": "Thai Express", "available": True},
            {"id": str(uuid.uuid4()), "name": "Sushi Platter", "category": "Asian", "price": 16.99, "image": "https://images.unsplash.com/photo-1579584425555-c3ce17fd4351?w=400&h=300&fit=crop", "description": "Assorted sushi rolls", "restaurant": "Sushi Master", "available": True},
            {"id": str(uuid.uuid4()), "name": "BBQ Ribs", "category": "BBQ", "price": 15.99, "image": "https://images.unsplash.com/photo-1544025162-d76694265947?w=400&h=300&fit=crop", "description": "Tender ribs with BBQ sauce", "restaurant": "Grill House", "available": True},
            {"id": str(uuid.uuid4()), "name": "Chicken Tikka", "category": "Asian", "price": 13.99, "image": "https://images.unsplash.com/photo-1599487488170-d11ec9c172f0?w=400&h=300&fit=crop", "description": "Spicy Indian chicken", "restaurant": "Curry House", "available": True},
            {"id": str(uuid.uuid4()), "name": "Pasta Carbonara", "category": "Italian", "price": 11.99, "image": "https://images.unsplash.com/photo-1612874742237-6526221588e3?w=400&h=300&fit=crop", "description": "Creamy pasta with bacon", "restaurant": "Italian Corner", "available": True},
            {"id": str(uuid.uuid4()), "name": "Fresh Fruit Bowl", "category": "Salads", "price": 6.99, "image": "https://images.unsplash.com/photo-1564093497595-593b96d80180?w=400&h=300&fit=crop", "description": "Mixed seasonal fruits", "restaurant": "Green Bowl", "available": True},
        ]
        await db.food_items.insert_many(food_items)
    
    # Seed some coupons
    coupon_count = await db.coupons.count_documents({})
    if coupon_count == 0:
        coupons = [
            {"id": str(uuid.uuid4()), "code": "WELCOME10", "discount_type": "percentage", "discount_value": 10, "min_order_value": 15, "max_discount": 5, "valid_until": "2026-12-31", "active": True},
            {"id": str(uuid.uuid4()), "code": "SAVE5", "discount_type": "fixed", "discount_value": 5, "min_order_value": 20, "max_discount": None, "valid_until": "2026-12-31", "active": True},
            {"id": str(uuid.uuid4()), "code": "FIRSTORDER", "discount_type": "percentage", "discount_value": 15, "min_order_value": 25, "max_discount": 10, "valid_until": "2026-12-31", "active": True},
        ]
        await db.coupons.insert_many(coupons)

# ============ AUTH ROUTES ============

@api_router.post("/auth/register", response_model=User)
async def register(user_data: UserRegister):
    # Check if user exists
    existing = await db.users.find_one({"email": user_data.email}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    user_id = str(uuid.uuid4())
    hashed_pwd = hash_password(user_data.password)
    
    user_doc = {
        "id": user_id,
        "name": user_data.name,
        "email": user_data.email,
        "password": hashed_pwd,
        "user_type": user_data.user_type,
        "phone": None,
        "address": None,
        "is_available": True
    }
    
    await db.users.insert_one(user_doc)
    
    return User(**{k: v for k, v in user_doc.items() if k != "password"})

@api_router.post("/auth/login")
async def login(credentials: UserLogin):
    user = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    
    if not user or not verify_password(credentials.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    token = create_token(user["id"], user["email"], user["user_type"])
    
    return {
        "token": token,
        "user": User(**{k: v for k, v in user.items() if k != "password"})
    }

# ============ FOOD ROUTES ============

@api_router.get("/food/items", response_model=List[FoodItem])
async def get_food_items(category: Optional[str] = None):
    query = {"available": True}
    if category and category != "All":
        query["category"] = category
    
    items = await db.food_items.find(query, {"_id": 0}).to_list(1000)
    return items

@api_router.get("/food/categories")
async def get_categories():
    categories = await db.food_items.distinct("category")
    return {"categories": ["All"] + sorted(categories)}

# ============ COUPON ROUTES ============

@api_router.post("/coupons/validate")
async def validate_coupon(data: CouponValidate):
    coupon = await db.coupons.find_one(
        {"code": data.code.upper(), "active": True},
        {"_id": 0}
    )
    
    if not coupon:
        raise HTTPException(status_code=404, detail="Invalid coupon code")
    
    if data.order_total < coupon["min_order_value"]:
        raise HTTPException(
            status_code=400,
            detail=f"Minimum order value of ${coupon['min_order_value']} required"
        )
    
    if coupon["discount_type"] == "percentage":
        discount = (data.order_total * coupon["discount_value"]) / 100
        if coupon.get("max_discount"):
            discount = min(discount, coupon["max_discount"])
    else:
        discount = coupon["discount_value"]
    
    return {
        "valid": True,
        "discount_amount": round(discount, 2),
        "coupon": coupon
    }

@api_router.get("/coupons", response_model=List[Coupon])
async def get_coupons():
    coupons = await db.coupons.find({"active": True}, {"_id": 0}).to_list(1000)
    return coupons

@api_router.post("/coupons/create", response_model=Coupon)
async def create_coupon(coupon_data: CouponCreate):
    coupon_id = str(uuid.uuid4())
    coupon_doc = {
        "id": coupon_id,
        "code": coupon_data.code.upper(),
        "discount_type": coupon_data.discount_type,
        "discount_value": coupon_data.discount_value,
        "min_order_value": coupon_data.min_order_value,
        "max_discount": coupon_data.max_discount,
        "valid_until": coupon_data.valid_until,
        "active": True
    }
    
    await db.coupons.insert_one(coupon_doc)
    return Coupon(**coupon_doc)

# ============ ORDER ROUTES ============

@api_router.post("/orders/create", response_model=Order)
async def create_order(order_data: OrderCreate, token: str):
    try:
        payload = decode_token(token)
        user_id = payload["user_id"]
        
        user = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        order_id = str(uuid.uuid4())
        order_doc = {
            "id": order_id,
            "customer_id": user_id,
            "customer_name": user["name"],
            "items": [item.model_dump() for item in order_data.items],
            "total": order_data.total,
            "payment_method": order_data.payment_method,
            "delivery_address": order_data.delivery_address,
            "coupon_code": order_data.coupon_code,
            "discount_amount": order_data.discount_amount,
            "status": "Placed",
            "delivery_person_id": None,
            "delivery_person_name": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "rating": None,
            "review": None
        }
        
        await db.orders.insert_one(order_doc)
        return Order(**order_doc)
    except:
        raise HTTPException(status_code=401, detail="Invalid token")

@api_router.get("/orders/my-orders", response_model=List[Order])
async def get_my_orders(token: str):
    payload = decode_token(token)
    user_id = payload["user_id"]
    
    orders = await db.orders.find(
        {"customer_id": user_id},
        {"_id": 0}
    ).sort("timestamp", -1).to_list(1000)
    
    return orders

@api_router.get("/orders/{order_id}", response_model=Order)
async def get_order(order_id: str):
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@api_router.post("/orders/{order_id}/review")
async def add_review(order_id: str, review_data: OrderReview, token: str):
    payload = decode_token(token)
    
    result = await db.orders.update_one(
        {"id": order_id},
        {"$set": {"rating": review_data.rating, "review": review_data.review}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return {"success": True, "message": "Review added successfully"}

# ============ ADMIN ROUTES ============

@api_router.get("/admin/orders", response_model=List[Order])
async def get_all_orders(token: str, status: Optional[str] = None):
    payload = decode_token(token)
    if payload["user_type"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    query = {}
    if status:
        query["status"] = status
    
    orders = await db.orders.find(query, {"_id": 0}).sort("timestamp", -1).to_list(1000)
    return orders

@api_router.patch("/admin/orders/{order_id}/status")
async def update_order_status(order_id: str, status_data: OrderStatusUpdate, token: str):
    payload = decode_token(token)
    if payload["user_type"] not in ["admin", "delivery_person"]:
        raise HTTPException(status_code=403, detail="Unauthorized")
    
    result = await db.orders.update_one(
        {"id": order_id},
        {"$set": {"status": status_data.status}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return {"success": True, "message": "Order status updated"}

@api_router.patch("/admin/orders/{order_id}/assign-delivery")
async def assign_delivery_person(order_id: str, assignment: DeliveryAssignment, token: str):
    payload = decode_token(token)
    if payload["user_type"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Get delivery person
    delivery_person = await db.users.find_one(
        {"id": assignment.delivery_person_id, "user_type": "delivery_person"},
        {"_id": 0}
    )
    
    if not delivery_person:
        raise HTTPException(status_code=404, detail="Delivery person not found")
    
    result = await db.orders.update_one(
        {"id": order_id},
        {"$set": {
            "delivery_person_id": assignment.delivery_person_id,
            "delivery_person_name": delivery_person["name"],
            "status": "Assigned"
        }}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    
    return {"success": True, "message": "Delivery person assigned"}

@api_router.get("/admin/delivery-persons", response_model=List[User])
async def get_delivery_persons(token: str):
    payload = decode_token(token)
    if payload["user_type"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    delivery_persons = await db.users.find(
        {"user_type": "delivery_person"},
        {"_id": 0, "password": 0}
    ).to_list(1000)
    
    return delivery_persons

@api_router.get("/admin/stats")
async def get_stats(token: str):
    payload = decode_token(token)
    if payload["user_type"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    total_orders = await db.orders.count_documents({})
    total_revenue = 0
    
    orders = await db.orders.find({}, {"_id": 0, "total": 1}).to_list(10000)
    for order in orders:
        total_revenue += order["total"]
    
    total_customers = await db.users.count_documents({"user_type": "customer"})
    total_items = await db.food_items.count_documents({"available": True})
    
    return {
        "total_orders": total_orders,
        "total_revenue": round(total_revenue, 2),
        "total_customers": total_customers,
        "total_items": total_items
    }

# ============ DELIVERY PERSON ROUTES ============

@api_router.get("/delivery/my-orders", response_model=List[Order])
async def get_delivery_orders(token: str):
    payload = decode_token(token)
    if payload["user_type"] != "delivery_person":
        raise HTTPException(status_code=403, detail="Delivery person access required")
    
    orders = await db.orders.find(
        {"delivery_person_id": payload["user_id"]},
        {"_id": 0}
    ).sort("timestamp", -1).to_list(1000)
    
    return orders

# ============ APP INITIALIZATION ============

@app.on_event("startup")
async def startup_event():
    await seed_data()
    logger.info("Application started and data seeded")

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
