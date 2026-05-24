import os
import json
import tempfile
import shutil
import zipfile
from pathlib import Path
from typing import List, Optional, Dict, Any
import logging

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, APIRouter, Depends, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool
import asyncio
import aiofiles
from pydantic import BaseModel
import uvicorn
from dotenv import load_dotenv
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from code_reviewer import CodeReviewer
from patch_utils import PatchValidator, validate_code_content, PatchApplicabilityChecker, ASTValidator, FileGroundingValidator
from image_processor import ImageProcessor, load_image_from_path

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Contextual Code Review Assistant", description="A multimodal code reviewer powered by Gemma 4")

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

security = HTTPBearer(auto_error=False)

def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    expected_api_key = os.getenv("API_KEY")
    if not expected_api_key:
        return True # Auth is disabled
        
    if not credentials or credentials.credentials != expected_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API Key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials

env_mode = os.getenv("ENVIRONMENT", "development")
cors_origins = ["*"] if env_mode == "development" else [os.getenv("FRONTEND_URL", "http://localhost:5173")]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

reviewer = CodeReviewer()

class HealthResponse(BaseModel):
    status: str
    model: str
    mock_mode: bool

class ReviewResponse(BaseModel):
    summary: str
    root_cause: str
    fix_plan: List[str]
    patch: Optional[str] = None
    assumptions: List[str] = []
    confidence: Optional[str] = None
    patch_validation: Optional[Dict[str, Any]] = None
    patch_warning: Optional[str] = None
    patch_applicable: Optional[bool] = None
    patch_applicable_message: Optional[str] = None
    ast_valid: Optional[bool] = None
    ast_error: Optional[str] = None
    file_grounding: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    details: Optional[List[str]] = None

class VisualDiffResponse(BaseModel):
    alignment_score: float
    num_regions: int
    confidence: str
    regions: List[Dict[str, Any]]
    impact: Dict[str, Any]
    filtered_pixel_count: int
    raw_pixel_count: int
    anti_aliased_filtered: int

api_router = APIRouter(prefix="/api")

@api_router.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="healthy",
        model=os.getenv('MODEL_CHOICE', 'gemma-4-31b'),
        mock_mode=reviewer.mock_mode
    )

@api_router.post("/visual-diff", response_model=VisualDiffResponse, dependencies=[Depends(verify_api_key)])
@limiter.limit("10/minute")
async def visual_diff(
    request: Request,
    image_before: UploadFile = File(...),
    image_after: UploadFile = File(...),
    pixel_threshold: float = Form(45.0),
    spatial_threshold: int = Form(3),
    anti_aliasing_filter: bool = Form(True)
):
    """
    Perform sophisticated visual diff analysis with region clustering and anti-aliasing filtering.
    
    This endpoint implements the advanced pipeline:
    1. Computes per-pixel delta heatmap
    2. Applies spatial threshold and region clustering
    3. Filters anti-aliased differences (font anti-aliasing, small color dithers)
    4. Assesses layout geometry and accessibility impact
    5. Returns confidence level based on detected regions
    """
    try:
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Save uploaded images
            img_before_path = os.path.join(temp_dir, f"before_{image_before.filename}")
            img_after_path = os.path.join(temp_dir, f"after_{image_after.filename}")
            
            with open(img_before_path, "wb") as f:
                f.write(await image_before.read())
            with open(img_after_path, "wb") as f:
                f.write(await image_after.read())
            
            # Load images using the image processor
            def process_images_sync():
                img1 = load_image_from_path(img_before_path)
                img2 = load_image_from_path(img_after_path)
                
                # Initialize processor with provided parameters
                processor = ImageProcessor(
                    pixel_threshold=pixel_threshold,
                    spatial_threshold=spatial_threshold,
                    anti_aliasing_filter=anti_aliasing_filter
                )
                
                # Run the full pipeline
                result = processor.process_images(img1, img2)
                
                # Convert regions to serializable format (convert numpy types to native Python)
                regions_serializable = []
                for region in result["regions"]:
                    regions_serializable.append({
                        "x": int(region.x),
                        "y": int(region.y),
                        "width": int(region.width),
                        "height": int(region.height),
                        "pixel_count": int(region.pixel_count),
                        "avg_diff": float(region.avg_diff),
                        "max_diff": float(region.max_diff),
                        "bbox": tuple(int(x) for x in region.bbox)
                    })
                
                return {
                    "alignment_score": float(result["alignment_score"]),
                    "num_regions": int(result["num_regions"]),
                    "confidence": result["confidence"],
                    "regions": regions_serializable,
                    "impact": result["impact"],
                    "filtered_pixel_count": int(result["filtered_pixel_count"]),
                    "raw_pixel_count": int(result["raw_pixel_count"]),
                    "anti_aliased_filtered": int(result["anti_aliased_filtered"])
                }
            
            # Run image processing in threadpool to avoid blocking
            diff_result = await run_in_threadpool(process_images_sync)
            
            return VisualDiffResponse(**diff_result)
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Exception during visual-diff endpoint: {e}", exc_info=True)
        if os.getenv("ENVIRONMENT", "development") == "production":
             raise HTTPException(status_code=500, detail="Internal server error")
        else:
             raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/review", response_model=ReviewResponse, dependencies=[Depends(verify_api_key)])
@limiter.limit("5/minute")
async def review(
    request: Request,
    files: List[UploadFile] = File(default=[]),
    images: List[UploadFile] = File(default=[]),
    context: str = Form(""),
    model: Optional[str] = Form(None)
):
    """Review uploaded code files and screenshots"""
    try:
        if not files and not images:
            raise HTTPException(status_code=400, detail="No files or images uploaded")
            
        temp_dir = tempfile.mkdtemp()
        file_paths = []
        image_paths = []
        
        def extract_zip(zip_path, ext_dir):
            extracted = []
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                for zip_info in zip_ref.infolist():
                    if zip_info.filename.startswith('/') or '..' in zip_info.filename:
                        continue
                    ext_path = zip_ref.extract(zip_info, ext_dir)
                    if not Path(ext_path).name.startswith('.') and Path(ext_path).is_file():
                        extracted.append(ext_path)
            return extracted

        try:
            # Save uploaded code files
            for file in files:
                if file.filename:
                    filename = Path(file.filename).name
                    file_path = os.path.join(temp_dir, filename)
                    content = await file.read()
                    async with aiofiles.open(file_path, "wb") as f:
                        await f.write(content)
                    
                    if filename.endswith('.zip'):
                        try:
                            extract_dir = os.path.join(temp_dir, f"extracted_{filename}")
                            os.makedirs(extract_dir, exist_ok=True)
                            
                            # Safe extraction to prevent Zip Slip in a threadpool
                            extracted_files = await asyncio.to_thread(extract_zip, file_path, extract_dir)
                            file_paths.extend(extracted_files)
                        except zipfile.BadZipFile:
                            raise HTTPException(status_code=400, detail=f"Invalid ZIP file: {filename}")
                    else:
                        file_paths.append(file_path)
                        
            # Save uploaded screenshot images
            for img in images:
                if img and img.filename:
                    filename = Path(img.filename).name
                    ext = Path(filename).suffix.lower()
                    if ext in ['.png', '.jpg', '.jpeg', '.webp', '.gif']:
                        img_path = os.path.join(temp_dir, filename)
                        content = await img.read()
                        async with aiofiles.open(img_path, "wb") as f:
                            await f.write(content)
                        image_paths.append(img_path)
                        
            # Validate uploaded code files if present
            if file_paths:
                validation = await run_in_threadpool(validate_code_content, file_paths)
                if validation.get('errors'):
                    raise HTTPException(status_code=400, detail=f"File validation failed: {validation['errors']}")
                    
            # Run code review
            result = await reviewer.review_files(file_paths, context, image_paths, model)
            
            # Validate patch if generated
            if result.get('patch'):
                def validate_patch_sync(patch, file_paths):
                    validator = PatchValidator()
                    file_context = {
                        Path(fp).name: reviewer._read_file_sync(fp)
                        for fp in file_paths
                    }
                    
                    # 1. Base safety check
                    safety_res = validator.validate_patch(patch, file_context)
                    
                    # 2. Applicability check
                    app_res = PatchApplicabilityChecker.check_applicability(patch, file_context)
                    
                    # 3. AST check
                    ast_res = ASTValidator.validate_patched_files(patch, file_context)
                    
                    # 4. File grounding check
                    ground_res = FileGroundingValidator.validate_grounding(patch, file_paths)
                    
                    return {
                        "patch_validation": safety_res,
                        "patch_applicable": app_res.get("applicable"),
                        "patch_applicable_message": app_res.get("message"),
                        "ast_valid": ast_res.get("valid"),
                        "ast_error": ", ".join(ast_res.get("errors", [])) if ast_res.get("errors") else None,
                        "file_grounding": ground_res
                    }
                    
                val_results = await run_in_threadpool(validate_patch_sync, result['patch'], file_paths)
                result['patch_validation'] = val_results['patch_validation']
                result['patch_applicable'] = val_results['patch_applicable']
                result['patch_applicable_message'] = val_results['patch_applicable_message']
                result['ast_valid'] = val_results['ast_valid']
                result['ast_error'] = val_results['ast_error']
                result['file_grounding'] = val_results['file_grounding']
                
                if not val_results['patch_validation'].get('is_safe', True):
                    result['patch_warning'] = 'Patch contains potentially unsafe operations or destructive commands. Review manually before applying.'
                    
            return ReviewResponse(**result)
            
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Exception during review endpoint: {e}", exc_info=True)
        if os.getenv("ENVIRONMENT", "development") == "production":
             raise HTTPException(status_code=500, detail="Internal server error")
        else:
             raise HTTPException(status_code=500, detail=str(e))

app.include_router(api_router)

# Serve frontend static files
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
examples_dir = os.path.join(os.path.dirname(__file__), "..", "examples")

if os.path.exists(examples_dir):
    app.mount("/examples", StaticFiles(directory=examples_dir), name="examples")

if os.path.exists(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")
    
    # Also mount other public files explicitly or via catch-all
    @app.get("/{file_path:path}")
    async def serve_frontend(file_path: str):
        full_path = os.path.join(frontend_dist, file_path)
        if os.path.exists(full_path) and os.path.isfile(full_path):
            return FileResponse(full_path)
        return FileResponse(os.path.join(frontend_dist, "index.html"))

if __name__ == '__main__':
    host = os.getenv('HOST') or os.getenv('FLASK_HOST') or '127.0.0.1'
    port = int(os.getenv('PORT') or os.getenv('FLASK_PORT') or 5000)
    env = os.getenv('ENVIRONMENT', 'development')
    logger.info(f"🚀 Starting Contextual Code Review Assistant on http://{host}:{port}")
    logger.info(f"📊 Using model: {os.getenv('MODEL_CHOICE', 'gemma-4-31b')}")
    logger.info(f"🔧 Mock Mode: {os.getenv('MOCK_MODE', 'false')}")
    logger.info(f"🌍 Environment: {env}")
    
    if not os.path.exists(frontend_dist):
        logger.warning(f"⚠️ Frontend dist directory not found at {frontend_dist}. Make sure to build the frontend.")
        
    uvicorn.run(app, host=host, port=port)
