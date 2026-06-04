from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from processor import process_gpx, process_json_data
import os
import json


app = FastAPI(title="GPX track processor")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

#get file from request, first as bytes then decode to a string. 
#then the processor will handle the string and return processed track_objects as a list of dicts.
@app.post("/upload-gpx")

async def upload_gpx(file: UploadFile = File(...)):
    
    bytes_content = await file.read()
    gpx_string = bytes_content.decode("utf-8")

    result = process_gpx(gpx_string)
    
    return {"status": "success", "data": result}

@app.post("/upload-json")
async def upload_json(data: dict = Body(...)):
    result = process_json_data(data)
    return {"status": "success", "data": result}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)), reload=True)

#for local testing.
# if __name__ == "__main__":
#     test_file_path = "renset_sejlads.gpx"
    
#     if os.path.exists(test_file_path):
#         with open(test_file_path, "r", encoding="utf-8") as f:
#             gpx_data = f.read()
        
#         print("🚀 Starter test af GPX processor...")

#         results = process_gpx(gpx_data)
        
#         print("\n--- TEST RESULTATER ---")
#         print(json.dumps(results, indent=4, ensure_ascii=False))
#     else:
#         print(f"❌ Filen {test_file_path} blev ikke fundet!")


# if __name__ == "__main__":
#     # Stien til din lokale fil
#     file_path = "13.05.2026 20.29.json"
    
#     if os.path.exists(file_path):
#         print(f"[*] Åbner fil: {file_path}")
#         with open(file_path, "r", encoding="utf-8") as f:
#             data = json.load(f)
            
#         print("[*] Sender data til processor...")
#         resultat = process_json_data(data)
#         print(f"[*] Resultat fra processor: {resultat}")
#     else:
#         print(f"[!] FEJL: Filen blev ikke fundet på stien: {file_path}")