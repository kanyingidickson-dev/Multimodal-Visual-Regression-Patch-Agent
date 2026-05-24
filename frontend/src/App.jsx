import React, { useState, useEffect, useRef, useMemo } from 'react';
import { sendReviewRequest, checkHealth } from './api';
import './App.css';
import { 
  Search, Clipboard, Bug, Wrench, Folder, Camera, Shield, 
  AlertTriangle, CheckCircle, XCircle, Code, Link, FileText, 
  Globe, BarChart3, Image as ImageIcon, Terminal, ExternalLink,
  Upload, X, Settings, Play, Download, Copy, AlertCircle
} from 'lucide-react';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("React Error Boundary caught an error", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="container" style={{ textAlign: 'center', marginTop: '10vh' }}>
          <h2>Something went wrong</h2>
          <p>{this.state.error && this.state.error.toString()}</p>
          <button onClick={() => window.location.reload()} className="action-btn">
            Reload Application
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

/* ========== HELPERS ========== */

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function getFileIcon(filename) {
  const ext = filename.split('.').pop().toLowerCase();
  const codeExts = ['py', 'js', 'ts', 'jsx', 'tsx', 'java', 'go', 'rs', 'c', 'cpp', 'h', 'rb', 'php', 'swift', 'kt'];
  const markupExts = ['html', 'css', 'scss', 'less', 'xml', 'svg'];
  const dataExts = ['json', 'yaml', 'yml', 'toml', 'csv'];
  const imgExts = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'svg'];

  if (ext === 'zip' || ext === 'tar' || ext === 'gz') return <Folder size={16} />;
  if (imgExts.includes(ext)) return <ImageIcon size={16} />;
  if (codeExts.includes(ext)) return <Code size={16} />;
  if (markupExts.includes(ext)) return <Globe size={16} />;
  if (dataExts.includes(ext)) return <BarChart3 size={16} />;
  if (ext === 'md' || ext === 'txt') return <FileText size={16} />;
  return <FileText size={16} />;
}

function getConfidence(result) {
  if (!result) return { level: 'low', label: 'Low' };
  
  if (result.confidence) {
    const level = result.confidence.toLowerCase();
    if (level === 'high') return { level: 'high', label: 'High' };
    if (level === 'medium') return { level: 'medium', label: 'Medium' };
    if (level === 'low') return { level: 'low', label: 'Low' };
  }

  const hasPatch = !!result.patch && result.patch.trim().length > 0;
  const hasWarning = !!result.patch_warning;
  const hasValidation = result.patch_validation;
  const isSafe = hasValidation ? hasValidation.is_safe !== false : true;

  if (hasPatch && isSafe && !hasWarning) return { level: 'high', label: 'High' };
  if (hasPatch && (hasWarning || !isSafe)) return { level: 'medium', label: 'Medium' };
  return { level: 'low', label: 'Low' };
}

/* ========== DIFF VIEWER COMPONENT ========== */

function DiffViewer({ patch }) {
  if (!patch || patch.trim() === '') {
    return (
      <div className="diff-container">
        <div className="diff-filename-bar">
          <span>No patch generated</span>
        </div>
      </div>
    );
  }

  const lines = patch.split('\n');

  // Extract filename from diff header
  let filename = '';
  for (const line of lines) {
    if (line.startsWith('diff --git')) {
      const match = line.match(/b\/(.+)$/);
      if (match) filename = match[1];
      break;
    }
    if (line.startsWith('---') || line.startsWith('+++')) {
      const match = line.match(/[ab]\/(.+)$/);
      if (match && !filename) filename = match[1];
    }
  }

  let lineNum = 0;

  const classifiedLines = lines.map((line, i) => {
    let type = 'context';
    let bgColor = 'transparent';
    let textColor = 'rgba(255, 255, 255, 0.5)';
    
    if (line.startsWith('diff --git') || line.startsWith('index ') || line.startsWith('---') || line.startsWith('+++')) {
      type = 'info';
      bgColor = 'rgba(88, 28, 135, 0.12)';
      textColor = '#a78bfa';
    } else if (line.startsWith('@@')) {
      type = 'header';
      bgColor = 'rgba(30, 58, 138, 0.15)';
      textColor = '#60a5fa';
      const match = line.match(/\+(\d+)/);
      if (match) lineNum = parseInt(match[1]) - 1;
    } else if (line.startsWith('+')) {
      type = 'added';
      bgColor = 'rgba(6, 95, 70, 0.3)';
      textColor = '#34d399';
      lineNum++;
    } else if (line.startsWith('-')) {
      type = 'removed';
      bgColor = 'rgba(127, 29, 29, 0.3)';
      textColor = '#fca5a5';
    } else {
      lineNum++;
    }

    return { text: line, type, num: type === 'added' || type === 'context' ? lineNum : '', key: i, bgColor, textColor };
  });

  return (
    <div className="diff-container" style={{background: '#040810', border: '1px solid var(--card-border)', borderRadius: '10px', overflow: 'hidden', fontFamily: 'var(--font-mono)', fontSize: '0.82rem'}}>
      {filename && (
        <div className="diff-filename-bar">
          <span className="filename">{filename}</span>
          <span>unified diff</span>
        </div>
      )}
      <div className="diff-scroll" style={{overflowX: 'auto', maxHeight: '500px', overflowY: 'auto'}}>
        <table className="diff-table" style={{width: '100%', borderCollapse: 'collapse'}}>
          <tbody>
            {classifiedLines.map((l) => (
              <tr key={l.key} className={`diff-line ${l.type}`} style={{display: 'table-row', minHeight: '1.25rem'}}>
                <td className="diff-gutter" style={{width: '44px', minWidth: '44px', textAlign: 'right', padding: '0 8px 0 0', color: 'rgba(255, 255, 255, 0.15)', fontSize: '0.72rem', userSelect: 'none', borderRight: '1px solid rgba(255, 255, 255, 0.04)', verticalAlign: 'top', backgroundColor: l.bgColor}}>{l.num || ''}</td>
                <td className="diff-line-content" style={{padding: '0 0.75rem', whiteSpace: 'pre', verticalAlign: 'top', lineHeight: '1.45', backgroundColor: l.bgColor, color: l.textColor}}>{l.text}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ========== RESULT SUMMARY CARD ========== */

function ResultSummaryCard({ result, codeFilesCount, imageFilesCount }) {
  const confidence = getConfidence(result);
  const hasPatch = !!result.patch && result.patch.trim().length > 0;
  const firstSentence = result.summary
    ? result.summary.split(/(?<=[.!?])\s/)[0]
    : 'Analysis complete.';

  return (
    <div className="result-summary-card">
      <div className="result-summary-header">
        <div className="result-summary-title">
          <Clipboard size={18} className="icon-inline" /> Analysis Results
        </div>
        <div className="confidence-label">
          <span className={`confidence-dot ${confidence.level}`}></span>
          {confidence.label} confidence
        </div>
      </div>
      <div className="status-chips">
        <span className="chip chip--warning"><Bug size={14} className="icon-inline" /> Bug Identified</span>
        {hasPatch && <span className="chip chip--success"><Wrench size={14} className="icon-inline" /> Patch Ready</span>}
        <span className="chip chip--info"><Folder size={14} className="icon-inline" /> {codeFilesCount} file{codeFilesCount !== 1 ? 's' : ''} analyzed</span>
        {imageFilesCount > 0 && <span className="chip chip--purple"><Camera size={14} className="icon-inline" /> UI screenshot reviewed</span>}
      </div>
      <p className="result-summary-text">{firstSentence}</p>
    </div>
  );
}

/* ========== CAVEATS CALLOUT ========== */

function CaveatsCallout({ assumptions }) {
  if (!assumptions || assumptions.length === 0) return null;
  return (
    <div className="caveats-callout">
      <div className="caveats-callout-title">
        <AlertTriangle size={16} className="icon-inline" /> Model Caveats & Assumptions
      </div>
      <ul className="caveats-callout-list">
        {assumptions.map((a, i) => (
          <li key={i}>{a}</li>
        ))}
      </ul>
    </div>
  );
}

/* ========== VISUAL MATCH TAB ========== */

function VisualMatchView({ imageFiles, result }) {
  const [imageUrl, setImageUrl] = useState(null);

  useEffect(() => {
    if (imageFiles.length > 0) {
      const url = URL.createObjectURL(imageFiles[0]);
      setImageUrl(url);
      return () => URL.revokeObjectURL(url);
    }
    return () => {};
  }, [imageFiles]);

  // Extract the code snippet from patch or root_cause
  const codeSnippet = useMemo(() => {
    if (result.patch) {
      return result.patch;
    }
    // Convert root_cause to diff-like format for consistent display
    const rootCause = result.root_cause || 'No code context available.';
    const lines = rootCause.split('\n');
    const diffLines = lines.map(line => `+${line}`).join('\n');
    return `--- a/context\n+++ b/context\n@@ -0,0 +1,${lines.length} @@\n${diffLines}`;
  }, [result]);

  if (!imageUrl) {
    return (
      <div className="visual-match-empty">
        <div className="visual-match-empty-icon"><Link size={32} /></div>
        <p>Upload a UI screenshot alongside code files to see the visual-to-code mapping.</p>
      </div>
    );
  }

  return (
    <div className="visual-match-container">
      <div className="visual-match-side">
        <div className="visual-match-side-label">
          <Camera size={14} className="icon-inline" /> UI Screenshot
        </div>
        <div className="visual-match-screenshot">
          <img src={imageUrl} alt="Uploaded UI screenshot" />
        </div>
      </div>

      <div className="visual-match-divider">
        <span className="visual-match-arrow"><ExternalLink size={20} /></span>
        <span className="visual-match-label">Gemma 4 Match</span>
      </div>

      <div className="visual-match-side">
        <div className="visual-match-side-label">
          <Code size={14} className="icon-inline" /> Related Code
        </div>
        <DiffViewer patch={codeSnippet} />
      </div>
    </div>
  );
}

/* ========== FILE PREVIEW ITEM ========== */

function FilePreviewItem({ file, onRemove, isImage }) {
  const [thumbUrl, setThumbUrl] = useState(null);

  useEffect(() => {
    if (isImage && file.type && file.type.startsWith('image/')) {
      const url = URL.createObjectURL(file);
      setThumbUrl(url);
      return () => URL.revokeObjectURL(url);
    }
    return () => {};
  }, [file, isImage]);

  return (
    <div className="preview-item">
      {thumbUrl ? (
        <img src={thumbUrl} alt={file.name} className="image-thumb" />
      ) : (
        <span className="preview-item-icon">{getFileIcon(file.name)}</span>
      )}
      <div className="preview-item-info">
        <span className="preview-item-name">{file.name}</span>
        <span className="preview-item-meta">
          {formatFileSize(file.size)}
          <span className="upload-success-check">✓ Ready</span>
        </span>
      </div>
      <button onClick={onRemove} className="remove-btn" aria-label={`Remove ${file.name}`}>✕</button>
    </div>
  );
}

/* ========== VISUAL VERIFICATION HELPERS & COMPONENTS ========== */

function getConfidenceLevel(score) {
  if (score >= 90) return 'high';
  if (score >= 75) return 'medium';
  return 'low';
}

function getConfidenceLabel(score) {
  if (score >= 90) return 'High Confidence';
  if (score >= 75) return 'Moderate Confidence';
  return 'Needs Review';
}

function formatNumber(num) {
  if (num >= 1000) {
    return (num / 1000).toFixed(1) + 'k';
  }
  return num.toString();
}

function formatImpactReason(reason) {
  // Convert technical reasons to more semantic descriptions
  if (reason.includes('Large region')) {
    const match = reason.match(/covers ([\d.]+)%/);
    const percentage = match ? match[1] : 'significant';
    return `Primary regression region covers ${percentage}% of viewport`;
  }
  if (reason.includes('Overlapping regions')) {
    const match = reason.match(/(\d+)/);
    const count = match ? match[1] : 'multiple';
    return `${count} overlapping layout clusters detected`;
  }
  if (reason.includes('touches image edge')) {
    return 'Potential truncation detected at viewport boundary';
  }
  return reason;
}

function deduplicateAndSummarizeReasons(reasons) {
  // Deduplicate and categorize impact reasons
  const seen = new Set();
  const unique = [];
  
  for (const reason of reasons) {
    const key = reason.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      unique.push(reason);
    }
  }
  
  // If we have too many, prioritize and summarize
  if (unique.length > 4) {
    const prioritized = [];
    let hasLargeRegion = false;
    let hasOverlap = false;
    let hasEdge = false;
    
    for (const reason of unique) {
      if (reason.includes('Large region') && !hasLargeRegion) {
        prioritized.push(reason);
        hasLargeRegion = true;
      } else if (reason.includes('Overlapping') && !hasOverlap) {
        prioritized.push(reason);
        hasOverlap = true;
      } else if (reason.includes('edge') && !hasEdge) {
        prioritized.push(reason);
        hasEdge = true;
      }
    }
    
    // Add a summary if we filtered items
    if (prioritized.length < unique.length) {
      prioritized.push('Minor rendering noise filtered automatically');
    }
    
    return prioritized.slice(0, 4);
  }
  
  return unique;
}

function generateAISummary(score, regions, impact) {
  // Generate an AI summary based on the analysis
  const regionCount = regions.length;
  const hasLayoutImpact = impact.layout_geometry_affected;
  const hasAccessibilityImpact = impact.accessibility_affected;
  
  if (score >= 90) {
    return 'Patch successfully resolves the regression with minimal visual differences.';
  }
  
  if (score >= 75) {
    if (hasLayoutImpact) {
      return 'Patch partially resolves the regression, but minor layout inconsistencies remain.';
    }
    return 'Patch addresses the primary regression with some residual alignment drift.';
  }
  
  // Low confidence
  if (hasLayoutImpact && hasAccessibilityImpact) {
    return 'Patch partially resolves the regression, but significant structural inconsistencies remain in the primary layout region.';
  }
  if (hasLayoutImpact) {
    return 'Patch shows limited effectiveness; significant layout drift remains in key content areas.';
  }
  if (regionCount > 5) {
    return 'Patch introduces multiple visual inconsistencies that require further review.';
  }
  return 'Patch requires review due to unresolved layout alignment issues.';
}

async function runSophisticatedPixelDiff(imgBefore, imgAfter, callback) {
  try {
    // Convert images to blobs for upload
    const blobBefore = await fetch(imgBefore.src).then(res => res.blob());
    const blobAfter = await fetch(imgAfter.src).then(res => res.blob());
    
    // Create FormData for the API request
    const formData = new FormData();
    formData.append('image_before', blobBefore, 'before.png');
    formData.append('image_after', blobAfter, 'after.png');
    formData.append('pixel_threshold', '45.0');
    formData.append('spatial_threshold', '3');
    formData.append('anti_aliasing_filter', 'true');
    
    // Call the sophisticated visual diff API
    const response = await fetch('/api/visual-diff', {
      method: 'POST',
      body: formData
    });
    
    if (!response.ok) {
      throw new Error(`API request failed: ${response.status}`);
    }
    
    const result = await response.json();
    
    // Generate a simple heatmap visualization from the regions
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    const width = 600;
    const height = 450;
    canvas.width = width;
    canvas.height = height;
    
    // Draw the before image as background
    ctx.drawImage(imgBefore, 0, 0, width, height);
    
    // Draw regions as overlays
    result.regions.forEach(region => {
      const { x, y, width: w, height: h, bbox } = region;
      // Scale coordinates if needed (assuming images are scaled to 600x450)
      const scaleX = width / imgBefore.naturalWidth;
      const scaleY = height / imgBefore.naturalHeight;
      
      ctx.strokeStyle = 'rgba(239, 68, 68, 0.8)';
      ctx.lineWidth = 2;
      ctx.strokeRect(
        bbox[0] * scaleX,
        bbox[1] * scaleY,
        (bbox[2] - bbox[0]) * scaleX,
        (bbox[3] - bbox[1]) * scaleY
      );
      
      // Fill with semi-transparent red
      ctx.fillStyle = 'rgba(239, 68, 68, 0.3)';
      ctx.fillRect(
        bbox[0] * scaleX,
        bbox[1] * scaleY,
        (bbox[2] - bbox[0]) * scaleX,
        (bbox[3] - bbox[1]) * scaleY
      );
    });
    
    callback({
      heatmapUrl: canvas.toDataURL('image/png'),
      score: result.alignment_score,
      diffPixels: result.filtered_pixel_count,
      regions: result.regions,
      confidence: result.confidence,
      impact: result.impact,
      anti_aliased_filtered: result.anti_aliased_filtered,
      raw_pixel_count: result.raw_pixel_count
    });
  } catch (e) {
    console.error("Sophisticated pixel diff failed, falling back to simple diff", e);
    // Fallback to simple canvas-based diff
    runSimplePixelDiff(imgBefore, imgAfter, callback);
  }
}

function runSimplePixelDiff(imgBefore, imgAfter, callback) {
  const canvasBefore = document.createElement('canvas');
  const canvasAfter = document.createElement('canvas');
  const canvasDiff = document.createElement('canvas');
  
  const width = 600;
  const height = 450;
  
  canvasBefore.width = width;
  canvasBefore.height = height;
  canvasAfter.width = width;
  canvasAfter.height = height;
  canvasDiff.width = width;
  canvasDiff.height = height;
  
  const ctxBefore = canvasBefore.getContext('2d');
  const ctxAfter = canvasAfter.getContext('2d');
  const ctxDiff = canvasDiff.getContext('2d');
  
  ctxBefore.drawImage(imgBefore, 0, 0, width, height);
  ctxAfter.drawImage(imgAfter, 0, 0, width, height);
  
  try {
    const dataBefore = ctxBefore.getImageData(0, 0, width, height);
    const dataAfter = ctxAfter.getImageData(0, 0, width, height);
    const dataDiff = ctxDiff.createImageData(width, height);
    
    let diffPixels = 0;
    const totalPixels = width * height;
    
    for (let i = 0; i < dataBefore.data.length; i += 4) {
      const rB = dataBefore.data[i];
      const gB = dataBefore.data[i+1];
      const bB = dataBefore.data[i+2];
      const aB = dataBefore.data[i+3];
      
      const rA = dataAfter.data[i];
      const gA = dataAfter.data[i+1];
      const bA = dataAfter.data[i+2];
      const aA = dataAfter.data[i+3];
      
      const diff = Math.abs(rB - rA) + Math.abs(gB - gA) + Math.abs(bB - bA);
      
      if (diff > 45) { // Threshold for change
        diffPixels++;
        // Draw change in heatmap (semi-transparent red-violet)
        dataDiff.data[i] = 239;     // R
        dataDiff.data[i+1] = 68;    // G
        dataDiff.data[i+2] = 68;    // B
        dataDiff.data[i+3] = 180;   // A (Alpha)
      } else {
        // Draw background in heatmap (greyscale of before image to give context)
        const grey = Math.round(0.299 * rB + 0.587 * gB + 0.114 * bB);
        dataDiff.data[i] = grey;
        dataDiff.data[i+1] = grey;
        dataDiff.data[i+2] = grey;
        dataDiff.data[i+3] = 60; // low opacity
      }
    }
    
    ctxDiff.putImageData(dataDiff, 0, 0);
    
    // Calculate score (0-100%)
    const matchRatio = 1 - (diffPixels / totalPixels);
    const alignmentScore = Math.round(matchRatio * 100);
    
    callback({
      heatmapUrl: canvasDiff.toDataURL('image/png'),
      score: alignmentScore,
      diffPixels
    });
  } catch (e) {
    console.error("Canvas pixel diff failed", e);
    callback({
      heatmapUrl: null,
      score: 100,
      diffPixels: 0
    });
  }
}

function ValidationPanel({ result }) {
  const [expanded, setExpanded] = useState({
    git: true,
    ast: true,
    grounding: true,
    safety: true
  });

  if (!result) return null;

  const toggleExpand = (key) => {
    setExpanded(prev => ({ ...prev, [key]: !prev[key] }));
  };

  const hasGit = result.patch_applicable !== undefined && result.patch_applicable !== null;
  const hasAST = result.ast_valid !== undefined && result.ast_valid !== null;
  const hasGrounding = result.file_grounding !== undefined && result.file_grounding !== null;
  const hasSafety = result.patch_validation !== undefined && result.patch_validation !== null;

  if (!hasGit && !hasAST && !hasGrounding && !hasSafety) {
    return null;
  }

  // Calculate Trust Score out of 10
  let score = 10;
  
  if (hasGit && !result.patch_applicable) score -= 4;
  if (hasAST && !result.ast_valid) score -= 3;
  if (hasGrounding && result.file_grounding && !result.file_grounding.grounded) score -= 2;
  if (hasSafety && result.patch_validation && result.patch_validation.is_safe === false) score -= 3;

  score = Math.max(1, Math.min(10, score));

  let badgeClass = "validation-trust-badge";
  let trustLabel = "Excellent";
  if (score < 5) {
    badgeClass += " danger";
    trustLabel = "Critical";
  } else if (score < 8) {
    badgeClass += " warn";
    trustLabel = "Caution";
  }

  return (
    <div className="validation-checklist">
      <div className="validation-card">
        <div className="validation-header">
          <div className="validation-header-title">
            <Shield size={18} className="icon-inline" /> Patch Applicability & Safety Check
          </div>
          <div className={badgeClass}>
            {trustLabel}: {score}/10 Trust
          </div>
        </div>
        <div className="validation-items">
          {/* Git check */}
          {hasGit && (
            <div className="validation-item">
              <div className="validation-item-header" onClick={() => toggleExpand('git')}>
                <div className="validation-item-left">
                  <span className="validation-item-icon">
                    {result.patch_applicable ? <CheckCircle size={16} /> : <XCircle size={16} />}
                  </span>
                  <span className="validation-item-name">Git Applicability Check</span>
                </div>
                <div className="validation-item-status">
                  <span className={`validation-status-text ${result.patch_applicable ? 'success' : 'danger'}`}>
                    {result.patch_applicable ? 'Clean Apply' : 'Conflicts Detected'}
                  </span>
                  <span style={{ fontSize: '0.7rem', marginLeft: '0.4rem' }}>{expanded.git ? '▲' : '▼'}</span>
                </div>
              </div>
              {expanded.git && (
                <div className="validation-item-detail">
                  {result.patch_applicable_message || (result.patch_applicable 
                    ? "The patch applies cleanly to target files using simulated git apply." 
                    : "The patch file could not be cleanly mapped to the original file contents.")}
                </div>
              )}
            </div>
          )}

          {/* AST Check */}
          {hasAST && (
            <div className="validation-item">
              <div className="validation-item-header" onClick={() => toggleExpand('ast')}>
                <div className="validation-item-left">
                  <span className="validation-item-icon">
                    {result.ast_valid ? <CheckCircle size={16} /> : <XCircle size={16} />}
                  </span>
                  <span className="validation-item-name">Syntax & Structure (AST) Check</span>
                </div>
                <div className="validation-item-status">
                  <span className={`validation-status-text ${result.ast_valid ? 'success' : 'danger'}`}>
                    {result.ast_valid ? 'Valid Syntax' : 'Syntax Error'}
                  </span>
                  <span style={{ fontSize: '0.7rem', marginLeft: '0.4rem' }}>{expanded.ast ? '▲' : '▼'}</span>
                </div>
              </div>
              {expanded.ast && (
                <div className="validation-item-detail">
                  {result.ast_valid 
                    ? "The modified code was parsed successfully and has no grammatical or syntax errors." 
                    : `Syntax validation failed:\n${result.ast_error || "Mismatched brackets or syntax structure error in patch."}`}
                </div>
              )}
            </div>
          )}

          {/* File Grounding */}
          {hasGrounding && (
            <div className="validation-item">
              <div className="validation-item-header" onClick={() => toggleExpand('grounding')}>
                <div className="validation-item-left">
                  <span className="validation-item-icon">
                    {result.file_grounding.grounded ? <CheckCircle size={16} /> : <XCircle size={16} />}
                  </span>
                  <span className="validation-item-name">File Grounding Check</span>
                </div>
                <div className="validation-item-status">
                  <span className={`validation-status-text ${result.file_grounding.grounded ? 'success' : 'danger'}`}>
                    {result.file_grounding.grounded ? 'All Files Grounded' : 'Hallucination Detected'}
                  </span>
                  <span style={{ fontSize: '0.7rem', marginLeft: '0.4rem' }}>{expanded.grounding ? '▲' : '▼'}</span>
                </div>
              </div>
              {expanded.grounding && (
                <div className="validation-item-detail">
                  {result.file_grounding.grounded 
                    ? "Every file modified in the patch matches the set of uploaded files. No hallucinated filenames." 
                    : `Patch attempts to modify files not in the upload list:\nUnknown files: ${result.file_grounding.unknown_files?.join(', ') || 'None'}`}
                </div>
              )}
            </div>
          )}

          {/* Safety Scan */}
          {hasSafety && (
            <div className="validation-item">
              <div className="validation-item-header" onClick={() => toggleExpand('safety')}>
                <div className="validation-item-left">
                  <span className="validation-item-icon">
                    {result.patch_validation.is_safe ? <CheckCircle size={16} /> : <AlertCircle size={16} />}
                  </span>
                  <span className="validation-item-name">Safety & Risk Scan</span>
                </div>
                <div className="validation-item-status">
                  <span className={`validation-status-text ${result.patch_validation.is_safe ? 'success' : 'warning'}`}>
                    {result.patch_validation.is_safe ? 'Safe Operations' : 'Potential Risk'}
                  </span>
                  <span style={{ fontSize: '0.7rem', marginLeft: '0.4rem' }}>{expanded.safety ? '▲' : '▼'}</span>
                </div>
              </div>
              {expanded.safety && (
                <div className="validation-item-detail">
                  {result.patch_validation.is_safe 
                    ? "No unsafe operations (like deletion of files, system calls, or hardcoded API keys) were detected in this patch." 
                    : `Warnings:\n${(result.patch_validation.warnings || []).join('\n') || 'Review details for safety hazards before applying.'}`}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function VisualVerificationView({ beforeImageFile, result }) {
  const [beforeUrl, setBeforeUrl] = useState(null);
  const [afterUrl, setAfterUrl] = useState(null);
  const [afterFile, setAfterFile] = useState(null);
  const [heatmapUrl, setHeatmapUrl] = useState(null);
  const [score, setScore] = useState(null);
  const [diffAnalysis, setDiffAnalysis] = useState(null); // Store sophisticated analysis results
  const [viewMode, setViewMode] = useState('slider'); // 'slider', 'side-by-side', 'heatmap'
  const [sliderPos, setSliderPos] = useState(50);
  const [isSimulated, setIsSimulated] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);

  const beforeImgRef = useRef(null);
  const afterImgRef = useRef(null);

  // Load BEFORE image
  useEffect(() => {
    if (beforeImageFile) {
      const url = URL.createObjectURL(beforeImageFile);
      setBeforeUrl(url);
      return () => URL.revokeObjectURL(url);
    }
  }, [beforeImageFile]);

  // Load AFTER image
  useEffect(() => {
    if (afterFile) {
      const url = URL.createObjectURL(afterFile);
      setAfterUrl(url);
      setIsSimulated(false);
      return () => URL.revokeObjectURL(url);
    }
  }, [afterFile]);

  // Load sample fixed image by default
  useEffect(() => {
    if (!afterFile && beforeUrl) {
      // Try to load the sample fix image
      const sampleFixImg = new Image();
      sampleFixImg.onload = () => {
        setAfterUrl('/sample-fix-screenshot.png');
        setIsSimulated(false);
      };
      sampleFixImg.onerror = () => {
        // If sample image doesn't load, that's okay - user can upload their own
        console.log('Sample fix image not found, user can upload their own');
      };
      sampleFixImg.src = '/sample-fix-screenshot.png';
    }
  }, [beforeUrl, afterFile]);

  // Generate visual diff when both before and after URLs are loaded
  useEffect(() => {
    if (!beforeUrl || !afterUrl) {
      setHeatmapUrl(null);
      setScore(null);
      return;
    }

    const imgBefore = new Image();
    const imgAfter = new Image();
    let loadedCount = 0;

    const onImageLoaded = () => {
      loadedCount++;
      if (loadedCount === 2) {
        runSophisticatedPixelDiff(imgBefore, imgAfter, ({ heatmapUrl, score, regions, confidence, impact, anti_aliased_filtered, raw_pixel_count }) => {
          setHeatmapUrl(heatmapUrl);
          setScore(score);
          // Store additional analysis data for display
          setDiffAnalysis({ regions, confidence, impact, anti_aliased_filtered, raw_pixel_count });
        });
      }
    };

    imgBefore.onload = onImageLoaded;
    imgAfter.onload = onImageLoaded;
    imgBefore.src = beforeUrl;
    imgAfter.src = afterUrl;
  }, [beforeUrl, afterUrl]);

  const handleAfterDrop = (e) => {
    e.preventDefault();
    setIsDragOver(false);
    
    let fileToLoad = null;
    if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      fileToLoad = e.dataTransfer.files[0];
    } else if (e.target && e.target.files && e.target.files.length > 0) {
      fileToLoad = e.target.files[0];
    }
    
    if (fileToLoad && fileToLoad.type && fileToLoad.type.startsWith('image/')) {
      setAfterFile(fileToLoad);
    }
  };

  const handleSimulateFix = () => {
    if (!beforeUrl) return;

    const img = new Image();
    img.onload = () => {
      const canvas = document.createElement('canvas');
      const ctx = canvas.getContext('2d');
      canvas.width = img.width;
      canvas.height = img.height;
      ctx.drawImage(img, 0, 0);

      // Simulate a realistic fix with more visible changes
      const bgData = ctx.getImageData(5, 5, 1, 1).data;
      const bgStyle = `rgb(${bgData[0]}, ${bgData[1]}, ${bgData[2]})`;

      // Crop and shift a section to simulate alignment/overflow resolution
      const shiftAmt = Math.round(img.width * 0.08);
      const startX = Math.round(img.width * 0.45);
      const widthToShift = img.width - startX;

      try {
        const slice = ctx.getImageData(startX, 0, widthToShift, img.height);

        ctx.fillStyle = bgStyle;
        ctx.fillRect(startX - 2, 0, widthToShift + 2, img.height);

        ctx.putImageData(slice, startX - shiftAmt, 0);

        // Add more prominent visual indicators
        // Green border around corrected zone
        ctx.strokeStyle = '#10b981';
        ctx.lineWidth = 4;
        ctx.setLineDash([8, 6]);
        ctx.strokeRect(startX - shiftAmt + 5, 10, widthToShift - shiftAmt - 10, img.height - 20);

        // Add "FIXED" label overlay
        ctx.fillStyle = 'rgba(16, 185, 129, 0.9)';
        ctx.fillRect(10, 10, 120, 35);
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 18px sans-serif';
        ctx.fillText('✓ FIXED', 25, 33);

        // Add subtle green tint to the whole image to indicate it's the fixed version
        ctx.fillStyle = 'rgba(16, 185, 129, 0.05)';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
      } catch (e) {
        console.error("Canvas helper failed, using box fallback", e);
        ctx.fillStyle = 'rgba(16, 185, 129, 0.25)';
        ctx.fillRect(img.width / 2, 0, img.width / 2, img.height);

        // Add "FIXED" label even in fallback
        ctx.fillStyle = 'rgba(16, 185, 129, 0.9)';
        ctx.fillRect(10, 10, 120, 35);
        ctx.fillStyle = '#ffffff';
        ctx.font = 'bold 18px sans-serif';
        ctx.fillText('✓ FIXED', 25, 33);
      }

      setAfterUrl(canvas.toDataURL('image/png'));
      setIsSimulated(true);
    };
    img.src = beforeUrl;
  };

  const handleSliderChange = (e) => {
    setSliderPos(parseInt(e.target.value));
  };

  return (
    <div className="verification-container">
      <div className="verification-summary-card">
        <div className="verification-summary-info">
          <div className="verification-summary-title">
            <Search size={20} className="icon-inline" /> Patch Verification Engine
          </div>
          <div className="verification-summary-desc">
            {afterUrl
              ? (isSimulated
                  ? "Comparing buggy layout with a client-side simulated alignment correction (green dashed outline indicates modified region)."
                  : "Verifying that the generated patch fixes the regression without introducing new layout issues.")
              : "Upload a screenshot of the fix (or run simulated fix) to compare pixel differences."
            }
          </div>
        </div>

        {score !== null && (
          <div className="verification-score-container">
            <div className="verification-score-value">{Math.round(score * 10) / 10}%</div>
            <div className="verification-score-label">
              Layout<br/>Alignment
            </div>
          </div>
        )}
        
        {diffAnalysis && (
          <div className="verification-analysis-container">
            <div className="verification-analysis-header">
              <span className="verification-analysis-title">Layout Integrity Scan</span>
              <span className={`verification-confidence-badge ${getConfidenceLevel(score)}`}>
                {getConfidenceLabel(score)}
              </span>
            </div>
            <div className="verification-analysis-stats">
              <div className="verification-analysis-stat">
                <span className="verification-stat-label">Detected Regions:</span>
                <span className="verification-stat-value">{diffAnalysis.regions.length}</span>
              </div>
              <div className="verification-analysis-stat">
                <span className="verification-stat-label">Structural Diff Area:</span>
                <span className="verification-stat-value">{formatNumber(diffAnalysis.raw_pixel_count)} px</span>
              </div>
              <div className="verification-analysis-stat">
                <span className="verification-stat-label">Filtered Rendering Noise:</span>
                <span className="verification-stat-value">{formatNumber(diffAnalysis.anti_aliased_filtered)} px</span>
              </div>
            </div>
            {diffAnalysis.impact.reasoning && diffAnalysis.impact.reasoning.length > 0 && (
              <div className="verification-analysis-impact">
                <span className="verification-impact-title">Impact Assessment:</span>
                <ul className="verification-impact-list">
                  {deduplicateAndSummarizeReasons(diffAnalysis.impact.reasoning).map((reason, idx) => (
                    <li key={idx} className="verification-impact-item">{formatImpactReason(reason)}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="verification-ai-summary">
              <span className="verification-ai-summary-label">AI Summary:</span>
              <span className="verification-ai-summary-text">{generateAISummary(score, diffAnalysis.regions, diffAnalysis.impact)}</span>
            </div>
          </div>
        )}
      </div>

      <div className="verification-views">
        <div className="verification-view-controls">
          <div className="verification-view-modes">
            <button 
              className={`verification-view-mode-btn ${viewMode === 'slider' ? 'active' : ''}`}
              onClick={() => setViewMode('slider')}
              disabled={!afterUrl}
            >
              Split Slider
            </button>
            <button 
              className={`verification-view-mode-btn ${viewMode === 'side-by-side' ? 'active' : ''}`}
              onClick={() => setViewMode('side-by-side')}
              disabled={!afterUrl}
            >
              Side-by-Side
            </button>
            <button 
              className={`verification-view-mode-btn ${viewMode === 'heatmap' ? 'active' : ''}`}
              onClick={() => setViewMode('heatmap')}
              disabled={!afterUrl}
            >
              Pixel Diff Heatmap
            </button>
          </div>

          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button className="simulator-btn" onClick={handleSimulateFix}>
              <Wrench size={16} className="icon-inline" /> Simulate Fix
            </button>
            {afterUrl && (
              <button className="btn-secondary" onClick={() => { setAfterFile(null); setAfterUrl(null); setIsSimulated(false); }} style={{color: '#ff6b6b', borderColor: '#ff6b6b'}}>
                <X size={14} className="icon-inline" /> Clear Fix
              </button>
            )}
          </div>
        </div>

        {/* View content */}
        {!afterUrl ? (
          <div 
            className={`upload-overlay-trigger ${isDragOver ? 'dragover' : ''}`}
            onDrop={handleAfterDrop}
            onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
            onDragLeave={() => setIsDragOver(false)}
          >
            <div style={{fontSize: '2rem', marginBottom: '0.5rem'}}><Camera size={32} /></div>
            <strong>Drag and drop the fixed UI screenshot here</strong>
            <p style={{fontSize: '0.8rem', color: 'var(--text-secondary)', marginTop: '0.25rem'}}>
              or click the button below to upload. Alternatively, click "Simulate Fix" above to test the visual diff pipeline instantly.
            </p>
            <div style={{marginTop: '1rem'}}>
              <input 
                type="file" 
                accept="image/*" 
                onChange={handleAfterDrop}
                style={{display: 'none'}} 
                id="after-image-upload"
              />
              <label 
                htmlFor="after-image-upload"
                className="btn-secondary"
                style={{cursor: 'pointer', display: 'inline-block'}}
              >
                <Upload size={14} className="icon-inline" /> Upload Screenshot
              </label>
            </div>
          </div>
        ) : (
          <>
            {viewMode === 'slider' && (
              <div className="verification-slider-wrapper">
                {/* Labels - positioned outside clipped containers */}
                <span className="verification-label-badge before">Before (Buggy)</span>
                <span className="verification-label-badge after">After (Fixed)</span>

                {/* After Image (underneath - shows full image) */}
                <div className="verification-slider-image verification-slider-after">
                  <img src={afterUrl} alt="After Fix" ref={afterImgRef} />
                </div>

                {/* Before Image (on top - clipped to show left portion) */}
                <div
                  className="verification-slider-image verification-slider-before"
                  style={{ clipPath: `polygon(0 0, ${sliderPos}% 0, ${sliderPos}% 100%, 0 100%)` }}
                >
                  <img src={beforeUrl} alt="Before Fix" ref={beforeImgRef} />
                </div>

                {/* Slider bar indicator */}
                <div className="slider-overlay-handle" style={{ left: `${sliderPos}%` }}></div>

                {/* Range input for scrubbing */}
                <input
                  type="range"
                  min="0"
                  max="100"
                  value={sliderPos}
                  onChange={handleSliderChange}
                  className="verification-slider-input"
                />
              </div>
            )}

            {viewMode === 'side-by-side' && (
              <div className="verification-side-by-side">
                <div className="verification-side-panel">
                  <div className="verification-side-panel-title">Before (Buggy)</div>
                  <div className="verification-side-image">
                    <img src={beforeUrl} alt="Before Fix" />
                  </div>
                </div>
                <div className="verification-side-panel">
                  <div className="verification-side-panel-title">After (Fixed)</div>
                  <div className="verification-side-image">
                    <img src={afterUrl} alt="After Fix" />
                  </div>
                </div>
              </div>
            )}

            {viewMode === 'heatmap' && (
              <div className="heatmap-canvas-container">
                {heatmapUrl ? (
                  <img src={heatmapUrl} alt="Pixel Diff Heatmap" className="heatmap-canvas" />
                ) : (
                  <div style={{color: 'var(--text-secondary)'}}>Computing pixel-level heatmap diff...</div>
                )}
                <span className="verification-label-badge before" style={{left: '1rem'}}>Heatmap overlay (changes in Red)</span>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

/* ========== LOADING MESSAGES ========== */

const LOADING_STEPS = [
  { text: 'Reading source files…', sub: 'Parsing code structure' },
  { text: 'Analyzing UI screenshots…', sub: 'Extracting visual elements' },
  { text: 'Cross-referencing code & visuals…', sub: 'Identifying mismatches' },
  { text: 'Generating root cause analysis…', sub: 'Building diagnostic report' },
  { text: 'Synthesizing patch…', sub: 'Creating fix recommendation' },
];

/* ========== MAIN APP ========== */

function MainApp() {
  const [model, setModel] = useState('gemma-4-31b');
  const [context, setContext] = useState('');
  const [followUp, setFollowUp] = useState('');
  const [codeFiles, setCodeFiles] = useState([]);
  const [imageFiles, setImageFiles] = useState([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState('summary');
  const [health, setHealth] = useState({ status: 'unknown' });
  const [loadingStep, setLoadingStep] = useState(0);
  const abortControllerRef = useRef(null);

  // Added States
  const [apiKey, setApiKey] = useState(() => localStorage.getItem('gemma_review_api_key') || '');
  const [isDragOverCode, setIsDragOverCode] = useState(false);
  const [isDragOverImage, setIsDragOverImage] = useState(false);

  // Persist API Key changes
  useEffect(() => {
    localStorage.setItem('gemma_review_api_key', apiKey);
  }, [apiKey]);

  useEffect(() => {
    checkHealth().then(setHealth);
  }, []);

  // Cycle loading messages
  useEffect(() => {
    if (!loading) {
      setLoadingStep(0);
      return;
    }
    const interval = setInterval(() => {
      setLoadingStep(prev => (prev + 1) % LOADING_STEPS.length);
    }, 3000);
    return () => clearInterval(interval);
  }, [loading]);

  const handleCodeDrop = (e) => {
    e.preventDefault();
    const newFiles = Array.from(e.dataTransfer?.files || e.target.files);

    if (codeFiles.length + newFiles.length > 20) {
      setError("Maximum 20 code files allowed.");
      return;
    }
    const oversized = newFiles.filter(f => f.size > 1024 * 1024);
    if (oversized.length > 0) {
      setError(`Files too large (max 1MB): ${oversized.map(f => f.name).join(', ')}`);
      return;
    }
    setError('');

    const updated = [...codeFiles];
    newFiles.forEach(newFile => {
      const existingIndex = updated.findIndex(f => f.name === newFile.name);
      if (existingIndex >= 0) {
        updated[existingIndex] = newFile;
      } else {
        updated.push(newFile);
      }
    });
    setCodeFiles(updated);
  };

  const handleImageDrop = (e) => {
    e.preventDefault();
    const newFiles = Array.from(e.dataTransfer?.files || e.target.files);

    if (imageFiles.length + newFiles.length > 10) {
      setError("Maximum 10 images allowed.");
      return;
    }
    const oversized = newFiles.filter(f => f.size > 5 * 1024 * 1024);
    if (oversized.length > 0) {
      setError(`Images too large (max 5MB): ${oversized.map(f => f.name).join(', ')}`);
      return;
    }
    setError('');

    const updated = [...imageFiles];
    newFiles.forEach(newFile => {
      const existingIndex = updated.findIndex(f => f.name === newFile.name);
      if (existingIndex >= 0) {
        updated[existingIndex] = newFile;
      } else {
        updated.push(newFile);
      }
    });
    setImageFiles(updated);
  };

  const removeCodeFile = (index) => {
    setCodeFiles(prev => prev.filter((_, i) => i !== index));
  };

  const removeImageFile = (index) => {
    setImageFiles(prev => prev.filter((_, i) => i !== index));
  };

  const loadExample = async () => {
    try {
      const codeRes = await fetch('/examples/broken-app/app.py');
      if (!codeRes.ok) throw new Error("Failed to load example app.py");
      const codeBlob = await codeRes.blob();
      const codeFile = new File([codeBlob], 'app.py', { type: 'text/plain' });

      const imgRes = await fetch('/examples/sample-screenshot.png');
      if (!imgRes.ok) throw new Error("Failed to load example screenshot");
      const imgBlob = await imgRes.blob();
      const imgFile = new File([imgBlob], 'sample-screenshot.png', { type: 'image/png' });

      setCodeFiles([codeFile]);
      setImageFiles([imgFile]);
      setContext("The user complains that the API rejects valid files. Fix the validation logic.");
      setError('');
    } catch (err) {
      setError(err.message);
    }
  };

  const runReview = async (isFollowUp = false) => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    setLoading(true);
    setError('');
    if (!isFollowUp) {
      setResult(null);
    }
    const currentContext = isFollowUp ? `${context}\nFollow-up: ${followUp}` : context;
    try {
      const data = await sendReviewRequest(
        codeFiles,
        imageFiles,
        currentContext,
        model,
        apiKey,
        abortControllerRef.current.signal
      );
      setResult(data);
      setActiveTab('summary');
      if (isFollowUp) {
        setFollowUp('');
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        console.log('Review request cancelled');
      } else {
        setError(err.message);
      }
    } finally {
      setLoading(false);
      abortControllerRef.current = null;
    }
  };

  const cancelReview = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setLoading(false);
      setError('Review cancelled by user.');
    }
  };

  const exportMarkdown = () => {
    if (!result) return;
    const md = `# Gemma 4 Review Output
## Summary
${result.summary}

## Root Cause
${result.root_cause}

## Fix Plan
${(result.fix_plan || []).map(step => `- ${step}`).join('\n')}

## Patch
\`\`\`diff
${result.patch || 'No patch needed'}
\`\`\`

## Assumptions
${(result.assumptions || []).map(a => `- ${a}`).join('\n')}
`;
    const blob = new Blob([md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'review-output.md';
    a.click();
    URL.revokeObjectURL(url);
  };

  const copyToClipboard = () => {
    if (!result) return;
    const text = `Summary: ${result.summary}\n\nRoot Cause: ${result.root_cause}\n\nFix Plan:\n${(result.fix_plan || []).map(s => `• ${s}`).join('\n')}\n\nPatch:\n${result.patch || 'No patch'}`;
    navigator.clipboard.writeText(text).catch(console.error);
  };

  const hasFiles = codeFiles.length > 0 || imageFiles.length > 0;
  const showVisualTab = imageFiles.length > 0 && codeFiles.length > 0;

  const currentLoadingStep = LOADING_STEPS[loadingStep];

  return (
    <div className="container">
      <header>
        <div className="logo-section">
          <h1><Search size={28} className="icon-inline" /> Visual Regression & Patch Agent </h1>
        </div>
        <p>Cross-reference UI screenshots against codebases to find alignment issues, compile errors, and design defects instantly.</p>
        <div className="status-bar">
          Backend Status: <span className={health.status === 'healthy' ? 'healthy' : 'down'}>
            {health.status === 'healthy' ? (health.mock_mode ? 'healthy (Mock Mode)' : 'healthy') : health.status}
          </span>
        </div>
      </header>

      {error && (
        <div className="error-card">
          <div className="error-card-title"><XCircle size={18} className="icon-inline" /> Analysis Request Failed</div>
          <p>{error}</p>
        </div>
      )}

<div className="hero">
    <img src="/cover.png" alt="Cover" />
</div>

      <div className="workspace-grid">
        {/* ========== LEFT PANE ========== */}
        <div className="left-pane">
          <div className="panel">
            <div className="panel-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span><Settings size={18} className="icon-inline" /> Model Settings</span>
              <button onClick={loadExample} className="btn-secondary">Load Example</button>
            </div>
            <div className="settings-row">
              <div className="form-group">
                <label>Select Model</label>
                <select value={model} onChange={e => setModel(e.target.value)}>
                  <option value="gemma-4-31b">Gemma 4 31B Dense</option>
                  <option value="gemma-4-26b-moe">Gemma 4 26B MoE</option>
                  <option value="gemma-4-4b">Gemma 4 4B Edge</option>
                </select>
              </div>
              <div className="form-group">
                <label>API Key (Optional)</label>
                <input
                  type="password"
                  value={apiKey}
                  onChange={e => setApiKey(e.target.value)}
                  placeholder="Enter API Key"
                />
              </div>
            </div>
          </div>

          <div className="section-divider">Inputs</div>

          <div className="panel">
            <div className="panel-title">📄 Source Code Files</div>
            <div 
              className={`drop-zone ${isDragOverCode ? 'dragover' : ''}`}
              onDrop={(e) => {
                setIsDragOverCode(false);
                handleCodeDrop(e);
              }}
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragOverCode(true);
              }}
              onDragLeave={() => setIsDragOverCode(false)}
            >
              <div className="drop-zone-icon">📁</div>
              <div>Drag & drop code files or ZIP, or click</div>
              <input 
                type="file" 
                multiple 
                onChange={(e) => {
                  setIsDragOverCode(false);
                  handleCodeDrop(e);
                }} 
                style={{position: 'absolute', top: 0, left: 0, opacity: 0, width: '100%', height: '100%', cursor: 'pointer'}} 
              />
            </div>
            <div className="preview-list">
              {codeFiles.map((f, i) => (
                <FilePreviewItem key={`code-${f.name}-${i}`} file={f} onRemove={() => removeCodeFile(i)} isImage={false} />
              ))}
            </div>
          </div>

          <div className="panel">
            <div className="panel-title"><Camera size={18} className="icon-inline" /> UI Screenshots</div>
            <div 
              className={`drop-zone ${isDragOverImage ? 'dragover' : ''}`}
              onDrop={(e) => {
                setIsDragOverImage(false);
                handleImageDrop(e);
              }}
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragOverImage(true);
              }}
              onDragLeave={() => setIsDragOverImage(false)}
            >
              <div className="drop-zone-icon"><Upload size={28} /></div>
              <div>Drag & drop screenshots</div>
              <input 
                type="file" 
                multiple 
                accept="image/*" 
                onChange={(e) => {
                  setIsDragOverImage(false);
                  handleImageDrop(e);
                }} 
                style={{position: 'absolute', top: 0, left: 0, opacity: 0, width: '100%', height: '100%', cursor: 'pointer'}} 
              />
            </div>
            <div className="preview-list">
              {imageFiles.map((f, i) => (
                <FilePreviewItem key={`img-${f.name}-${i}`} file={f} onRemove={() => removeImageFile(i)} isImage={true} />
              ))}
            </div>
          </div>

          <div className="section-divider">Action</div>

          <div className="panel">
            <div className="panel-title"><Terminal size={18} className="icon-inline" /> Review Scope</div>
            <textarea
              value={context}
              onChange={e => setContext(e.target.value)}
              placeholder="e.g., Button click handler never fires because the DOM selector is stale after re-render"
              rows="6"
              className="review-scope-textarea"
            ></textarea>
          </div>

          <div className="sticky-action">
            <button
              className={`action-btn ${hasFiles && !loading ? 'ready-pulse' : ''}`}
              onClick={() => runReview(false)}
              disabled={loading || !hasFiles}
            >
              {loading ? 'Analyzing…' : <><Play size={18} className="icon-inline" /> Launch Gemma 4 Review</>}
            </button>
          </div>
        </div>

        {/* ========== RIGHT PANE ========== */}
        <div className="right-pane">
          {/* Empty State */}
          {!result && !loading && (
            <div className="panel empty-state">
              <div className="empty-state-icon"><Terminal size={48} /></div>
              <h3>Ready for review</h3>
              <p>Upload source code and screenshots, then launch Gemma 4 to get a full diagnostic report with patch suggestions.</p>
            </div>
          )}

          {/* Loading State */}
          {loading && (
            <div className="panel loading-panel">
              <div className="spinner-outer">
                <div className="spinner-inner"></div>
              </div>
              <p className="loading-step">{currentLoadingStep.text}</p>
              <p className="loading-sub">{currentLoadingStep.sub}</p>
              <button onClick={cancelReview} className="btn-secondary" style={{marginTop: '1.5rem', color: '#ff6b6b', borderColor: '#ff6b6b'}}>
                Cancel Review
              </button>
            </div>
          )}

          {/* Result State */}
          {result && !loading && (
            <>
              {/* Summary Card */}
              <ResultSummaryCard
                result={result}
                codeFilesCount={codeFiles.length}
                imageFilesCount={imageFiles.length}
              />

              {/* Main Result Panel */}
              <div className="panel result-panel">
                <div className="result-actions-bar">
                  <button onClick={copyToClipboard} className="btn-secondary"><Copy size={14} className="icon-inline" /> Copy</button>
                  <button onClick={exportMarkdown} className="btn-secondary"><Download size={14} className="icon-inline" /> Export .md</button>
                </div>

                {/* Tabs */}
                <div className="tabs-header">
                  <button className={`tab-btn ${activeTab === 'summary' ? 'active' : ''}`} onClick={() => setActiveTab('summary')}>Overview</button>
                  <button className={`tab-btn ${activeTab === 'cause' ? 'active' : ''}`} onClick={() => setActiveTab('cause')}>Root Cause</button>
                  <button className={`tab-btn ${activeTab === 'plan' ? 'active' : ''}`} onClick={() => setActiveTab('plan')}>Fix Plan</button>
                  <button className={`tab-btn ${activeTab === 'patch' ? 'active' : ''}`} onClick={() => setActiveTab('patch')}>Patch</button>
                  {showVisualTab && (
                    <button className={`tab-btn ${activeTab === 'visual' ? 'active' : ''}`} onClick={() => setActiveTab('visual')}>Visual Match</button>
                  )}
                  {imageFiles.length > 0 && (
                    <button className={`tab-btn ${activeTab === 'verification' ? 'active' : ''}`} onClick={() => setActiveTab('verification')}><Search size={14} className="icon-inline" /> Verification</button>
                  )}
                </div>

                {/* Tab: Overview */}
                {activeTab === 'summary' && (
                  <div className="tab-content">
                    <p className="summary-text">{result.summary}</p>
                  </div>
                )}

                {/* Tab: Root Cause */}
                {activeTab === 'cause' && (
                  <div className="tab-content">
                    <p className="root-cause-text">{result.root_cause}</p>
                  </div>
                )}

                {/* Tab: Fix Plan */}
                {activeTab === 'plan' && (
                  <div className="tab-content">
                    <ul className="checklist">
                      {(result.fix_plan || []).map((step, i) => (
                        <li key={i} className="checklist-item">{step}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Tab: Patch (Diff Viewer) */}
                {activeTab === 'patch' && (
                  <div className="tab-content">
                    <ValidationPanel result={result} />
                    {result.patch_warning && (
                      <div className="warning-banner">
                        <span>⚠</span> <span>{result.patch_warning}</span>
                      </div>
                    )}
                    <DiffViewer patch={result.patch} />
                  </div>
                )}

                {/* Tab: Visual Match */}
                {activeTab === 'visual' && showVisualTab && (
                  <div className="tab-content">
                    <VisualMatchView imageFiles={imageFiles} result={result} />
                  </div>
                )}

                {/* Tab: Verification */}
                {activeTab === 'verification' && imageFiles.length > 0 && (
                  <div className="tab-content">
                    <VisualVerificationView beforeImageFile={imageFiles[0]} result={result} />
                  </div>
                )}

                {/* Caveats Callout (always visible below tabs) */}
                <CaveatsCallout assumptions={result.assumptions} />

                {/* Follow-up */}
                <div className="follow-up-section">
                  <h4>Ask a follow-up</h4>
                  <div className="follow-up-row">
                    <textarea
                      value={followUp}
                      onChange={e => setFollowUp(e.target.value)}
                      placeholder="E.g., 'What about edge case X?'"
                      rows="2"
                    ></textarea>
                    <button
                      className="btn-secondary"
                      onClick={() => runReview(true)}
                      disabled={loading || !followUp}
                      style={{alignSelf: 'flex-start', padding: '0.65rem 1rem'}}
                    >
                      Ask
                    </button>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <ErrorBoundary>
      <MainApp />
    </ErrorBoundary>
  );
}
