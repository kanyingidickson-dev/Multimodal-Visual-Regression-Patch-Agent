"""
Sophisticated image processing for visual regression detection
Implements spatial thresholding, region clustering, and anti-aliasing filtering
"""

import numpy as np
from typing import Tuple, List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class Region:
    """Represents a clustered region of pixel differences"""
    x: int
    y: int
    width: int
    height: int
    pixel_count: int
    avg_diff: float
    max_diff: float
    bbox: Tuple[int, int, int, int]  # (x1, y1, x2, y2)


class ImageProcessor:
    """
    Sophisticated image processor for visual regression detection.
    
    Pipeline:
    1. Compute per-pixel delta heatmap
    2. Apply spatial threshold to filter anti-aliased noise
    3. Region clustering via connected components
    4. Filter regions by size and significance
    5. Compute visual alignment score
    """
    
    def __init__(
        self,
        pixel_threshold: float = 45.0,
        spatial_threshold: int = 3,  # minimum region size in pixels
        anti_aliasing_filter: bool = True,
        min_region_area: int = 10,  # minimum pixels for a significant region
        max_region_area_ratio: float = 0.5,  # max region as fraction of image
    ):
        self.pixel_threshold = pixel_threshold
        self.spatial_threshold = spatial_threshold
        self.anti_aliasing_filter = anti_aliasing_filter
        self.min_region_area = min_region_area
        self.max_region_area_ratio = max_region_area_ratio
    
    def compute_pixel_diff(
        self, 
        img1: np.ndarray, 
        img2: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, float]:
        """
        Compute per-pixel difference between two images.
        
        Args:
            img1: First image (H, W, 3) RGB
            img2: Second image (H, W, 3) RGB
            
        Returns:
            diff_mask: Boolean mask where differences exceed threshold
            diff_values: Absolute difference values per pixel
            alignment_score: Overall visual alignment score (0-100)
        """
        # Ensure same shape
        if img1.shape != img2.shape:
            raise ValueError(f"Image shapes mismatch: {img1.shape} vs {img2.shape}")
        
        # Compute absolute difference per channel
        diff = np.abs(img1.astype(np.float32) - img2.astype(np.float32))
        
        # Sum RGB differences (Manhattan distance in color space)
        diff_sum = np.sum(diff, axis=2)
        
        # Apply pixel threshold
        diff_mask = diff_sum > self.pixel_threshold
        
        # Calculate alignment score
        total_pixels = img1.shape[0] * img1.shape[1]
        diff_pixels = np.sum(diff_mask)
        match_ratio = 1 - (diff_pixels / total_pixels)
        alignment_score = match_ratio * 100.0
        
        return diff_mask, diff_sum, alignment_score
    
    def filter_anti_aliased(
        self, 
        diff_mask: np.ndarray, 
        diff_values: np.ndarray
    ) -> np.ndarray:
        """
        Filter out anti-aliased differences (subtle pixel noise).
        
        Anti-aliased pixels typically:
        - Have small differences (just above threshold)
        - Are isolated or in very small clusters
        - Don't form coherent geometric shapes
        
        Args:
            diff_mask: Boolean mask of differences
            diff_values: Absolute difference values
            
        Returns:
            Filtered mask with anti-aliased noise removed
        """
        if not self.anti_aliasing_filter:
            return diff_mask
        
        # Create a copy to modify
        filtered_mask = diff_mask.copy()
        
        # Find pixels just above threshold (likely anti-aliasing)
        near_threshold = (diff_values > self.pixel_threshold) & \
                        (diff_values < self.pixel_threshold * 1.5)
        
        # Check if near-threshold pixels are isolated
        # Use 8-connectivity to check neighbors
        from scipy.ndimage import binary_erosion, binary_dilation
        
        # Erode to remove isolated pixels
        eroded = binary_erosion(near_threshold, structure=np.ones((3, 3)))
        
        # Pixels that were eroded away are isolated (anti-aliased)
        isolated_anti_aliased = near_threshold & (~eroded)
        
        # Remove isolated anti-aliased pixels
        filtered_mask[isolated_anti_aliased] = False
        
        return filtered_mask
    
    def cluster_regions(
        self, 
        diff_mask: np.ndarray,
        diff_values: np.ndarray
    ) -> List[Region]:
        """
        Cluster connected pixels into regions using connected components.
        
        Args:
            diff_mask: Boolean mask of differences
            diff_values: Absolute difference values
            
        Returns:
            List of Region objects
        """
        from scipy.ndimage import label, find_objects
        
        # Label connected components
        labeled_array, num_features = label(diff_mask)
        
        regions = []
        height, width = diff_mask.shape
        total_area = height * width
        
        for i in range(1, num_features + 1):
            # Get mask for this region
            region_mask = (labeled_array == i)
            pixel_count = np.sum(region_mask)
            
            # Skip regions that are too small
            if pixel_count < self.min_region_area:
                continue
            
            # Skip regions that are too large (likely major layout changes)
            if pixel_count > total_area * self.max_region_area_ratio:
                continue
            
            # Get bounding box
            rows, cols = np.where(region_mask)
            y1, y2 = rows.min(), rows.max()
            x1, x2 = cols.min(), cols.max()
            
            # Calculate statistics
            region_diffs = diff_values[region_mask]
            avg_diff = float(np.mean(region_diffs))
            max_diff = float(np.max(region_diffs))
            
            region = Region(
                x=x1,
                y=y1,
                width=x2 - x1 + 1,
                height=y2 - y1 + 1,
                pixel_count=int(pixel_count),
                avg_diff=avg_diff,
                max_diff=max_diff,
                bbox=(x1, y1, x2, y2)
            )
            regions.append(region)
        
        # Sort by pixel count (largest first)
        regions.sort(key=lambda r: r.pixel_count, reverse=True)
        
        return regions
    
    def check_layout_geometry_impact(
        self, 
        regions: List[Region],
        image_shape: Tuple[int, int]
    ) -> Dict[str, Any]:
        """
        Check if regions affect layout geometry or accessibility.
        
        Layout geometry impact indicators:
        - Large regions (> 5% of image)
        - Regions spanning significant width/height
        - Multiple regions in same area (overlap patterns)
        
        Accessibility impact indicators:
        - Contrast issues (high diff in text areas)
        - Overlap regions (elements overlapping)
        - Truncation (regions at edges)
        
        Args:
            regions: List of detected regions
            image_shape: (height, width) of image
            
        Returns:
            Dict with impact assessment
        """
        height, width = image_shape
        total_area = height * width
        
        impact = {
            "layout_geometry_affected": False,
            "accessibility_affected": False,
            "large_regions": [],
            "edge_regions": [],
            "overlap_regions": [],
            "reasoning": []
        }
        
        if not regions:
            return impact
        
        # Check for large regions (layout impact)
        for region in regions:
            region_area = region.pixel_count
            area_ratio = region_area / total_area
            
            if area_ratio > 0.05:  # > 5% of image
                impact["large_regions"].append({
                    "bbox": tuple(int(x) for x in region.bbox),
                    "area_ratio": float(area_ratio),
                    "pixel_count": int(region.pixel_count)
                })
                impact["layout_geometry_affected"] = True
                impact["reasoning"].append(
                    f"Large region at {tuple(int(x) for x in region.bbox)} covers {float(area_ratio):.1%} of image"
                )
        
        # Check for edge regions (truncation impact)
        for region in regions:
            x1, y1, x2, y2 = region.bbox
            margin = 10  # pixels from edge
            
            at_edge = (
                x1 <= margin or  # Left edge
                x2 >= width - margin or  # Right edge
                y1 <= margin or  # Top edge
                y2 >= height - margin  # Bottom edge
            )
            
            if at_edge:
                impact["edge_regions"].append(tuple(int(x) for x in region.bbox))
                impact["accessibility_affected"] = True
                impact["reasoning"].append(
                    f"Region at {tuple(int(x) for x in region.bbox)} touches image edge (possible truncation)"
                )
        
        # Check for overlapping regions (accessibility impact)
        if len(regions) > 1:
            # Simple overlap detection based on bounding boxes
            for i, r1 in enumerate(regions):
                for r2 in regions[i+1:]:
                    if self._bboxes_overlap(r1.bbox, r2.bbox):
                        impact["overlap_regions"].append(
                            (tuple(int(x) for x in r1.bbox), tuple(int(x) for x in r2.bbox))
                        )
                        impact["accessibility_affected"] = True
                        impact["reasoning"].append(
                            f"Overlapping regions: {tuple(int(x) for x in r1.bbox)} and {tuple(int(x) for x in r2.bbox)}"
                        )
        
        return impact
    
    def _bboxes_overlap(
        self, 
        bbox1: Tuple[int, int, int, int],
        bbox2: Tuple[int, int, int, int]
    ) -> bool:
        """Check if two bounding boxes overlap."""
        x1_1, y1_1, x2_1, y2_1 = bbox1
        x1_2, y1_2, x2_2, y2_2 = bbox2
        
        return not (x2_1 < x1_2 or x2_2 < x1_1 or y2_1 < y1_2 or y2_2 < y1_1)
    
    def compute_confidence(
        self,
        regions: List[Region],
        impact: Dict[str, Any],
        alignment_score: float
    ) -> str:
        """
        Compute confidence level based on detected regions and impact.
        
        Confidence levels:
        - high: Clear layout geometry or accessibility impact
        - medium: Some regions detected but impact unclear
        - low: Only small, isolated regions (likely anti-aliasing artifacts)
        
        Args:
            regions: List of detected regions
            impact: Impact assessment from check_layout_geometry_impact
            alignment_score: Overall visual alignment score
            
        Returns:
            Confidence level: "high", "medium", or "low"
        """
        # High confidence if layout geometry or accessibility is affected
        if impact["layout_geometry_affected"] or impact["accessibility_affected"]:
            return "high"
        
        # Medium confidence if there are significant regions
        if len(regions) > 0 and alignment_score < 95:
            return "medium"
        
        # Low confidence for minor differences
        return "low"
    
    def process_images(
        self,
        img1: np.ndarray,
        img2: np.ndarray
    ) -> Dict[str, Any]:
        """
        Full pipeline: compute diff, filter, cluster, and assess impact.
        
        Args:
            img1: First image (H, W, 3) RGB
            img2: Second image (H, W, 3) RGB
            
        Returns:
            Dict with complete analysis results
        """
        # Step 1: Compute pixel differences
        diff_mask, diff_values, alignment_score = self.compute_pixel_diff(img1, img2)
        
        # Step 2: Filter anti-aliased noise
        filtered_mask = self.filter_anti_aliased(diff_mask, diff_values)
        
        # Step 3: Cluster regions
        regions = self.cluster_regions(filtered_mask, diff_values)
        
        # Step 4: Check layout/accessibility impact
        impact = self.check_layout_geometry_impact(regions, img1.shape[:2])
        
        # Step 5: Compute confidence
        confidence = self.compute_confidence(regions, impact, alignment_score)
        
        return {
            "alignment_score": float(alignment_score),
            "diff_mask": filtered_mask,
            "diff_values": diff_values,
            "regions": regions,
            "num_regions": len(regions),
            "impact": impact,
            "confidence": confidence,
            "filtered_pixel_count": int(np.sum(filtered_mask)),
            "raw_pixel_count": int(np.sum(diff_mask)),
            "anti_aliased_filtered": int(np.sum(diff_mask) - np.sum(filtered_mask))
        }


def load_image_from_path(image_path: str) -> np.ndarray:
    """
    Load image from file path as numpy array.
    
    Args:
        image_path: Path to image file
        
    Returns:
        Image as numpy array (H, W, 3) RGB
    """
    try:
        from PIL import Image
        img = Image.open(image_path)
        # Convert to RGB if needed
        if img.mode != 'RGB':
            img = img.convert('RGB')
        return np.array(img)
    except ImportError:
        raise ImportError(
            "PIL/Pillow is required for image loading. "
            "Install with: pip install Pillow"
        )


def load_image_from_bytes(image_bytes: bytes) -> np.ndarray:
    """
    Load image from bytes as numpy array.
    
    Args:
        image_bytes: Image data as bytes
        
    Returns:
        Image as numpy array (H, W, 3) RGB
    """
    try:
        from PIL import Image
        import io
        img = Image.open(io.BytesIO(image_bytes))
        if img.mode != 'RGB':
            img = img.convert('RGB')
        return np.array(img)
    except ImportError:
        raise ImportError(
            "PIL/Pillow is required for image loading. "
            "Install with: pip install Pillow"
        )
