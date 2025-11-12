const express = require('express');
const multer = require('multer');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs').promises;
const fsSync = require('fs');
const { v4: uuidv4 } = require('uuid');

// Load environment variables
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 3000;
const SHIFTN_PATH = process.env.SHIFTN_PATH || '/app/shiftn';
const SHIFTN_EXE = path.join(SHIFTN_PATH, 'ShiftN.exe');
const IS_LINUX = process.platform === 'linux'; // Detect if running on Linux

// Create temp directories if they don't exist
const UPLOAD_DIR = path.join(__dirname, 'temp', 'uploads');
const OUTPUT_DIR = path.join(__dirname, 'temp', 'outputs');

async function ensureDirectories() {
    await fs.mkdir(UPLOAD_DIR, { recursive: true });
    await fs.mkdir(OUTPUT_DIR, { recursive: true });
}

ensureDirectories();

// Configure multer for file uploads
const storage = multer.diskStorage({
    destination: UPLOAD_DIR,
    filename: (req, file, cb) => {
        const uniqueName = `${uuidv4()}${path.extname(file.originalname)}`;
        cb(null, uniqueName);
    }
});

const upload = multer({
    storage,
    limits: { fileSize: 50 * 1024 * 1024 }, // 50MB limit
    fileFilter: (req, file, cb) => {
        const allowedTypes = /jpeg|jpg|png|bmp|tiff|tif/;
        const extname = allowedTypes.test(path.extname(file.originalname).toLowerCase());
        const mimetype = allowedTypes.test(file.mimetype);
        
        if (extname && mimetype) {
            cb(null, true);
        } else {
            cb(new Error('Only image files are allowed (JPEG, PNG, BMP, TIFF)'));
        }
    }
});

// Middleware
app.use(express.json());

// CORS middleware - allow requests from browser test client
app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
    res.header('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept, Authorization, X-API-Key');
    
    // Handle preflight requests
    if (req.method === 'OPTIONS') {
        return res.sendStatus(200);
    }
    
    next();
});

// API Key authentication middleware
const authenticate = (req, res, next) => {
    const apiKey = req.headers['x-api-key'] || req.query.api_key;
    
    if (!process.env.API_KEY) {
        return res.status(500).json({ 
            error: 'Server configuration error: API_KEY not configured' 
        });
    }
    
    if (!apiKey) {
        return res.status(401).json({ 
            error: 'Missing API key. Provide via X-API-Key header or api_key query parameter.' 
        });
    }
    
    if (apiKey !== process.env.API_KEY) {
        return res.status(401).json({ 
            error: 'Invalid API key' 
        });
    }
    
    next();
};

// Process image with ShiftN
async function processImage(inputPath, outputPath, option = 'A2') {
    return new Promise((resolve, reject) => {
        const outputDir = path.dirname(outputPath);
        const outputFilename = path.basename(outputPath);
        
        // Use Wine on Linux, direct execution on Windows
        const command = IS_LINUX ? 'wine' : SHIFTN_EXE;
        const args = IS_LINUX 
            ? [SHIFTN_EXE, inputPath, outputFilename, option]
            : [inputPath, outputFilename, option];
        
        console.log(`Executing: ${command} ${args.join(' ')}`);
        
        const childProcess = spawn(command, args, {
            cwd: outputDir,
            shell: true,
            env: {
                ...process.env,
                WINEDEBUG: '-all' // Suppress Wine debug messages
            }
        });
        
        let stderr = '';
        let stdout = '';
        let processCompleted = false;
        
        childProcess.stdout.on('data', (data) => {
            stdout += data.toString();
        });
        
        childProcess.stderr.on('data', (data) => {
            stderr += data.toString();
        });
        
        // Expected output file (ShiftN always creates .bmp files)
        const bmpOutput = outputPath.replace(path.extname(outputPath), '.bmp');
        
        // File polling function to check for output
        let pollCount = 0;
        let lastFileSize = 0;
        const maxPolls = 200; // 10 minutes max (3000ms * 200)
        
        const pollForFile = setInterval(() => {
            pollCount++;
            
            try {
                if (fsSync.existsSync(bmpOutput)) {
                    const stats = fsSync.statSync(bmpOutput);
                    const currentSize = stats.size;
                    
                    // Check if file size is stable (not still being written)
                    if (currentSize > 0 && currentSize === lastFileSize) {
                        // File exists and size is stable - processing complete!
                        clearInterval(pollForFile);
                        
                        if (!processCompleted) {
                            processCompleted = true;
                            console.log(`ShiftN completed successfully. Output: ${bmpOutput} (${currentSize} bytes)`);
                            
                            // Kill the ShiftN process immediately since its job is done
                            console.log('Killing ShiftN process...');
                            if (!childProcess.killed) {
                                childProcess.kill('SIGTERM');
                                setTimeout(() => {
                                    if (!childProcess.killed) {
                                        childProcess.kill('SIGKILL');
                                    }
                                }, 2000);
                            }
                            
                            // Convert BMP to JPEG for smaller file size and better compatibility
                            const jpegOutput = bmpOutput.replace('.bmp', '.jpg');
                            
                            // Use ImageMagick to convert BMP to JPEG
                            const convertProcess = spawn('convert', [
                                bmpOutput,
                                '-quality', '90',
                                jpegOutput
                            ]);
                            
                            let convertError = '';
                            
                            convertProcess.stderr.on('data', (data) => {
                                convertError += data.toString();
                            });
                            
                            convertProcess.on('close', async (code) => {
                                if (code === 0 && fsSync.existsSync(jpegOutput)) {
                                    console.log(`Converted BMP to JPEG: ${jpegOutput}`);
                                    
                                    // Delete the original BMP file
                                    try {
                                        await fs.unlink(bmpOutput);
                                        console.log(`Deleted original BMP: ${bmpOutput}`);
                                    } catch (unlinkErr) {
                                        console.error('Error deleting BMP:', unlinkErr);
                                    }
                                    
                                    resolve(jpegOutput);
                                } else {
                                    console.error('BMP to JPEG conversion failed:', convertError);
                                    
                                    // Fall back to original BMP if conversion fails
                                    resolve(bmpOutput);
                                }
                            });
                            
                            convertProcess.on('error', (error) => {
                                console.error('ImageMagick convert process error:', error);
                                
                                // Fall back to original BMP if conversion fails
                                resolve(bmpOutput);
                            });
                        }
                        return;
                    }
                    
                    lastFileSize = currentSize;
                } else if (pollCount >= maxPolls) {
                    // Timeout reached
                    clearInterval(pollForFile);
                    
                    if (!processCompleted) {
                        processCompleted = true;
                        
                        // Kill the process
                        if (!childProcess.killed) {
                            childProcess.kill('SIGKILL');
                        }
                        
                        reject(new Error(`ShiftN timeout: No output file created after ${maxPolls * 3000}ms. STDERR: ${stderr}`));
                    }
                }
            } catch (error) {
                // Continue polling if file system error (file might be locked)
                console.log(`Polling error (attempt ${pollCount}): ${error.message}`);
            }
        }, 3000); // Poll every 3 seconds
        
        // Handle process errors (startup failures)
        childProcess.on('error', (error) => {
            clearInterval(pollForFile);
            if (!processCompleted) {
                processCompleted = true;
                reject(new Error(`Failed to start ShiftN: ${error.message}`));
            }
        });
        
        // Handle clean process exit (mainly for Windows)
        childProcess.on('close', (code) => {
            if (!processCompleted) {
                console.log(`ShiftN process exited with code ${code}`);
                if (stdout) console.log('STDOUT:', stdout);
                if (stderr) console.log('STDERR:', stderr);
                
                // Don't clear interval here - let file polling handle completion
                // This allows the same logic to work for both clean exits and hanging processes
            }
        });
    });
}

// Cleanup old files
async function cleanupOldFiles(directory, maxAgeMs = 3600000) {
    try {
        const files = await fs.readdir(directory);
        const now = Date.now();
        
        for (const file of files) {
            const filePath = path.join(directory, file);
            const stats = await fs.stat(filePath);
            
            if (now - stats.mtimeMs > maxAgeMs) {
                await fs.unlink(filePath);
            }
        }
    } catch (error) {
        console.error('Cleanup error:', error);
    }
}

// Run cleanup every hour
setInterval(() => {
    cleanupOldFiles(UPLOAD_DIR);
    cleanupOldFiles(OUTPUT_DIR);
}, 3600000);

// Routes
app.get('/health', (req, res) => {
    res.json({ 
        status: 'healthy', 
        shiftNPath: SHIFTN_PATH,
        shiftNExists: fsSync.existsSync(SHIFTN_EXE)
    });
});

app.post('/correct', authenticate, upload.single('image'), async (req, res) => {
    console.log('=== UPLOAD REQUEST DEBUG ===');
    console.log('Request method:', req.method);
    console.log('Content-Type:', req.get('Content-Type'));
    console.log('Body keys:', Object.keys(req.body));
    console.log('File object:', req.file ? 'EXISTS' : 'MISSING');
    
    if (req.file) {
        console.log('File details:', {
            originalname: req.file.originalname,
            filename: req.file.filename,
            path: req.file.path,
            size: req.file.size,
            mimetype: req.file.mimetype
        });
        console.log('File exists on disk:', fsSync.existsSync(req.file.path));
    } else {
        console.log('No file in request - checking for upload errors');
        console.log('Request files:', req.files);
        console.log('Request body:', req.body);
    }
    console.log('=== END DEBUG ===');
    
    if (!req.file) {
        return res.status(400).json({ error: 'No image file provided' });
    }
    
    const inputPath = req.file.path;
    const option = req.body.option || 'A2';
    const outputFilename = `${uuidv4()}.jpg`;
    const outputPath = path.join(OUTPUT_DIR, outputFilename);
    
    console.log('Processing setup:', {
        inputPath,
        outputPath,
        option,
        inputExists: fsSync.existsSync(inputPath)
    });
    
    try {
        const resultPath = await processImage(inputPath, outputPath, option);
        
        // Send the corrected image
        res.sendFile(resultPath, async (err) => {
            if (err) {
                console.error('Error sending file:', err);
            } else {
                console.log('File sent successfully:', resultPath);
            }
            
            // Clean up files after sending
            try {
                await fs.unlink(inputPath);
                await fs.unlink(resultPath);
                console.log('Cleanup completed for:', inputPath, resultPath);
            } catch (cleanupErr) {
                console.error('Cleanup error:', cleanupErr);
            }
        });
        
    } catch (error) {
        console.error('Processing error:', error);
        
        // Clean up input file on error
        try {
            if (fsSync.existsSync(inputPath)) {
                await fs.unlink(inputPath);
                console.log('Cleaned up input file after error:', inputPath);
            }
        } catch (cleanupErr) {
            console.error('Cleanup error:', cleanupErr);
        }
        
        res.status(500).json({ 
            error: 'Failed to process image', 
            details: error.message 
        });
    }
});

app.get('/', (req, res) => {
    res.json({
        service: 'ShiftN Perspective Correction API',
        version: '1.0.0',
        endpoints: {
            health: 'GET /health - Check service health',
            correct: 'POST /correct - Correct perspective in image (multipart/form-data with "image" field)'
        },
        options: {
            A1: 'Automatic correction mode 1',
            A2: 'Automatic correction mode 2 (default)',
            A3: 'Automatic correction mode 3'
        }
    });
});

app.listen(PORT, () => {
    console.log(`ShiftN API listening on port ${PORT}`);
    console.log(`ShiftN executable: ${SHIFTN_EXE}`);
    console.log(`Exists: ${fsSync.existsSync(SHIFTN_EXE)}`);
});
