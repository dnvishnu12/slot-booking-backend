import os
from fastapi import FastAPI, HTTPException
from pymongo import MongoClient
from pydantic import BaseModel
from typing import List, Dict
from urllib.parse import quote_plus
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

# username = os.getenv("MONGO_USERNAME")
# password = os.getenv("MONGO_PASSWORD")
# encoded_username = quote_plus(username)
# encoded_password = quote_plus(password)

client = MongoClient(f"mongodb+srv://dnvishnu:Fu99NSbZqN8wN4ks@cluster0.yeodlfo.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
db = client["slotbook"]

class_collection = db["class_list"]
booking_collection = db["booking_list"]

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ClassList(BaseModel):
    class_name: str
    class_id: str
    class_description: str
    icon: str
    color: str
    total_slots: int
    bookings: int = 0
    waitlist: int = 0

class Booking(BaseModel):
    class_id: str
    class_name: str
    user_name: str
    user_id: str
    booking_date: str

class CancelBookingRequest(BaseModel):
    class_id: str
    user_id: str

@app.get("/")
async def health_check():
    return {"status": "API is running"}

@app.get("/test-cors")
async def test_cors():
    return {"message": "CORS is working"}

@app.post("/create_class/")
async def create_class(class_data: ClassList):
    if class_collection.find_one({"class_id": class_data.class_id}):
        raise HTTPException(status_code=400, detail="Class ID already exists")
    
    class_collection.insert_one(class_data.dict())
    return {"message": "Class created successfully"}

@app.post("/book_slot/")
async def book_slot(booking: Booking):
    class_info = class_collection.find_one({"class_id": booking.class_id})
    
    if not class_info:
        raise HTTPException(status_code=404, detail="Class not found")
    
    booking_data = booking.dict()
    booking_data["class_name"] = class_info["class_name"]

    if class_info['bookings'] >= class_info['total_slots']:
        booking_collection.update_one(
            {"class_id": booking.class_id},
            {"$push": {"waitlist": booking_data}},
            upsert=True
        )
        class_collection.update_one(
            {"class_id": booking.class_id},
            {"$inc": {"waitlist": 1}}
        )
        return {"message": "Added to waitlist"}
    
    booking_collection.update_one(
        {"class_id": booking.class_id},
        {"$push": {"bookings": booking_data}},
        upsert=True
    )
    class_collection.update_one(
        {"class_id": booking.class_id},
        {"$inc": {"bookings": 1}}
    )
    
    return {"message": "Booking confirmed"}

@app.post("/cancel_booking/")
async def cancel_booking(request: CancelBookingRequest):
    class_id = request.class_id
    user_id = request.user_id
    
    booking_info = booking_collection.find_one({"class_id": class_id})
    
    if not booking_info:
        raise HTTPException(status_code=404, detail="Class not found")

    current_bookings_count = len(booking_info.get("bookings", []))

    result = booking_collection.update_one(
        {"class_id": class_id},
        {"$pull": {"bookings": {"user_id": user_id}}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    bookings_removed = current_bookings_count - len(booking_collection.find_one({"class_id": class_id}).get("bookings", []))
    
    update_result = class_collection.update_one(
        {"class_id": class_id},
        {"$inc": {"bookings": -bookings_removed}}
    )
    
    if update_result.modified_count == 0:
        raise HTTPException(status_code=500, detail="Failed to update class bookings")

    if booking_info.get("waitlist") and len(booking_info["waitlist"]) > 0:
        waitlist_entry = booking_info["waitlist"][0]
        booking_collection.update_one(
            {"class_id": class_id},
            {
                "$push": {"bookings": waitlist_entry},
                "$pull": {"waitlist": waitlist_entry}
            }
        )
        class_collection.update_one(
            {"class_id": class_id},
            {"$inc": {"waitlist": -1, "bookings": 1}}
        )
        return {"message": "Booking canceled, waitlist updated"}
    
    return {"message": "Booking canceled successfully"}

@app.get("/class_list/")
async def fetch_class_list():
    try:
        classes = list(class_collection.find({}))
        for cls in classes:
            cls["_id"] = str(cls["_id"])
        return {"classes": classes}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/user_bookings/{user_id}")
async def fetch_user_bookings(user_id: str):
    bookings = booking_collection.find({"bookings.user_id": user_id})
    results = []
    
    for class_info in bookings:
        for booking in class_info.get("bookings", []):
            if booking["user_id"] == user_id:
                results.append({
                    "class_id": class_info["class_id"],
                    "class_name": booking["class_name"],
                    "booking_date": booking["booking_date"]
                })
    
    if not results:
        raise HTTPException(status_code=404, detail="No bookings found for this user")
    
    return {"user_bookings": results}
