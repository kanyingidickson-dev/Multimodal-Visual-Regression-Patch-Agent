import json
from pathlib import Path
from typing import List, Dict, Optional

from gemma_client import GemmaClient
from file_parser import read_file, read_file_sync, truncate_content, encode_image
from prompt_templates import build_prompt

class CodeReviewer:
    """Multimodal code reviewer powered by Gemma 4"""
    
    def __init__(self):
        self.client = GemmaClient()
        
    @property
    def mock_mode(self):
        return self.client.mock_mode

    @mock_mode.setter
    def mock_mode(self, value):
        self.client.mock_mode = value

    def _read_file_sync(self, file_path: str) -> str:
        return read_file_sync(file_path)

    async def _read_file(self, file_path: str) -> str:
        return await read_file(file_path)
    
    def _parse_response(self, response: str) -> Dict:
        """Parse model response into structured format"""
        cleaned_response = response.strip()
        if cleaned_response.startswith("```json"):
            cleaned_response = cleaned_response[7:]
        elif cleaned_response.startswith("```"):
            cleaned_response = cleaned_response[3:]
        
        if cleaned_response.endswith("```"):
            cleaned_response = cleaned_response[:-3]
            
        try:
            start_idx = cleaned_response.find('{')
            end_idx = cleaned_response.rfind('}') + 1
            
            if start_idx != -1 and end_idx > start_idx:
                json_str = cleaned_response[start_idx:end_idx]
                parsed = json.loads(json_str)
                
                # Coerce fix_plan to list to prevent validation errors
                if 'fix_plan' in parsed and isinstance(parsed['fix_plan'], str):
                    parsed['fix_plan'] = [parsed['fix_plan']]
                elif 'fix_plan' not in parsed:
                    parsed['fix_plan'] = []
                
                # Parse, validate or derive confidence field
                confidence = str(parsed.get('confidence', '')).strip().lower()
                if confidence not in ['high', 'medium', 'low']:
                    if parsed.get('patch') and 'diff --git' in str(parsed.get('patch', '')):
                        parsed['confidence'] = 'high'
                    elif parsed.get('fix_plan') and len(parsed['fix_plan']) > 0:
                        parsed['confidence'] = 'medium'
                    else:
                        parsed['confidence'] = 'low'
                else:
                    parsed['confidence'] = confidence
                
                return parsed
        except Exception as e:
            pass
        
        return {
            'summary': response[:500] if len(response) > 500 else response,
            'root_cause': "Failed to parse structured JSON from model response",
            'fix_plan': ["Examine the raw response model text output"],
            'patch': None,
            'assumptions': [],
            'confidence': 'low'
        }
    
    async def review_files(self, file_paths: List[str], context: str = "", image_paths: Optional[List[str]] = None, model: Optional[str] = None) -> Dict:
        files_data = []
        for path in file_paths:
            content = await self._read_file(path)
            content = truncate_content(content)
            files_data.append({
                'name': Path(path).name,
                'content': content
            })
            
        encoded_images = []
        if image_paths:
            for img_path in image_paths:
                b64_img = await encode_image(img_path)
                if b64_img:
                    encoded_images.append(b64_img)
        
        system_prompt, user_prompt = build_prompt(files_data, context)
        import asyncio
        response = await asyncio.to_thread(self.client.call_model, system_prompt, user_prompt, encoded_images, model)
        result = self._parse_response(response)
        
        return result
