const API_URL = import.meta.env.VITE_API_URL || '/api';

export async function checkHealth() {
    try {
        const response = await fetch(`${API_URL}/health`);
        return await response.json();
    } catch (e) {
        console.error("Health check failed", e);
        return { status: 'down' };
    }
}

export async function sendReviewRequest(files, images, context, model, apiKey = null, signal = null) {
    const formData = new FormData();
    
    // Convert FileList or arrays to formData
    if (files && files.length > 0) {
        Array.from(files).forEach(file => formData.append('files', file));
    }
    
    if (images && images.length > 0) {
        Array.from(images).forEach(img => formData.append('images', img));
    }
    
    if (context) {
        formData.append('context', context);
    }
    
    if (model) {
        formData.append('model', model);
    }
    
    const maxRetries = 3;
    const baseDelayMs = 1000;
    
    for (let attempt = 0; attempt < maxRetries; attempt++) {
        try {
            const headers = {};
            if (apiKey) {
                headers['Authorization'] = `Bearer ${apiKey}`;
            }
            
            const response = await fetch(`${API_URL}/review`, {
                method: 'POST',
                headers,
                body: formData,
                signal,
            });
            
            if (!response.ok) {
                // If it's a 500 error and we haven't exhausted retries, try again
                if (response.status >= 500 && attempt < maxRetries - 1) {
                    throw new Error(`Transient Server Error: ${response.status}`);
                }
                
                let errStr = `HTTP error! status: ${response.status}`;
                try {
                    const err = await response.json();
                    if (err.detail) {
                        if (typeof err.detail === 'string') {
                            errStr = err.detail;
                        } else if (Array.isArray(err.detail)) {
                            errStr = err.detail.map(d => d.msg || d.type || JSON.stringify(d)).join(', ');
                        } else {
                            errStr = JSON.stringify(err.detail);
                        }
                    } else {
                        errStr = err.error || err.details || errStr;
                    }
                } catch(err) {
                    console.error("Failed to parse error response:", err);
                }
                
                // Do not retry 4xx errors
                const finalError = new Error(errStr);
                finalError.status = response.status;
                throw finalError;
            }
            
            return await response.json();
        } catch (err) {
            // If it's an abort error, throw immediately
            if (err.name === 'AbortError') {
                throw err;
            }
            // If it's the last attempt or a non-5xx error, throw
            if (attempt === maxRetries - 1 || (err.status && err.status < 500)) {
                throw err;
            }
            // Wait before next attempt (exponential backoff)
            const delay = baseDelayMs * Math.pow(2, attempt);
            console.log(`Request failed, retrying in ${delay}ms... (Attempt ${attempt + 1}/${maxRetries})`);
            await new Promise(resolve => setTimeout(resolve, delay));
        }
    }
}
