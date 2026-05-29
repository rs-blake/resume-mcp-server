# ResumeUp Resume Tailoring MCP Server

A **Model Context Protocol (MCP) server** that automates the process of uploading a resume, providing a job description, and tailoring the resume to match job requirements using the **ResumeUp.ai** platform via Playwright browser automation.

## Overview

This project converts a Playwright-based browser automation script into a composable MCP server with well-defined tools that LLMs (like Claude or Copilot) can call to orchestrate the resume tailoring workflow interactively.

### Key Features

✅ **Browser Automation**: Uses Playwright for reliable ResumeUp.ai interaction  
✅ **MCP Tools**: ResumeUp-only tools including one-shot `tailor_and_download`  
✅ **Session Management**: Persistent browser sessions with UUID tracking  
✅ **Job Parsing**: Intelligent extraction of skills, requirements, and company info  
✅ **Score Polling**: Automated re-analysis loops until target score reached  
✅ **PDF Download**: Automatic tailored resume extraction and download  
✅ **LinkedIn Job Search**: Search Easy Apply jobs and scrape posting details  
✅ **Search & Tailor Pipeline**: Auto-tailor resumes for matching LinkedIn jobs  
✅ **Application Review Queue**: Track tailored jobs before Easy Apply submission  
✅ **Easy Apply Assist Mode**: Pre-fill applications with tailored PDFs (manual submit by default)  
✅ **LLM Integration**: Ready for Copilot, Claude, or other MCP-compatible LLMs  

---

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/rs-blake/resume-mcp-server.git
cd resume-mcp-server
```

### 2. Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 4. Configure Environment

```bash
cp .env.example .env
# Edit .env with your ResumeUp credentials and settings
```

---

## MCP Tools Reference

### 1. `start_browser_session`
Start a new browser session and authenticate with ResumeUp.

**Input:**
```json
{
  "email": "your-email@example.com",  // optional
  "password": "your-password",         // optional
  "headless": false                    // optional
}
```

**Output:**
```json
{
  "success": true,
  "session_id": "uuid-string",
  "is_logged_in": true,
  "message": "Browser session started and authenticated"
}
```

---

### 2. `upload_resume`
Upload a local resume file or use an existing resume by ID.

**Input:**
```json
{
  "session_id": "uuid-string",
  "file_path": "/path/to/resume.pdf",  // optional if resume_id provided
  "resume_id": "resumeup-uuid"          // optional if file_path provided
}
```

**Output:**
```json
{
  "success": true,
  "resume_id": "uuid",
  "resume_preview": "First 500 characters of resume...",
  "message": "Resume uploaded successfully"
}
```

---

### 3. `parse_job_description`
Extract structured data from a job description (no browser session required).

**Input:**
```json
{
  "job_description_text": "Full job description text here..."
}
```

**Output:**
```json
{
  "success": true,
  "title": "Security Architect",
  "company": "Company Name",
  "key_skills": ["AWS", "Azure", "Kubernetes", "Security", "SIEM"],
  "requirements": ["3+ years experience", "AWS/Azure knowledge", ...],
  "nice_to_haves": ["Kubernetes experience", "ZTNA design", ...],
  "message": "Parsed job: Security Architect"
}
```

---

### 4. `upload_job_to_resumeup`
Enter job description in ResumeUp's Report tab.

**Input:**
```json
{
  "session_id": "uuid-string",
  "job_description_text": "Full job description..."
}
```

**Output:**
```json
{
  "success": true,
  "message": "Job description uploaded successfully"
}
```

---

### 5. `get_resume_score`
Fetch current resume score from ResumeUp.

**Input:**
```json
{
  "session_id": "uuid-string"
}
```

**Output:**
```json
{
  "success": true,
  "score": 82,
  "found": true,
  "message": "Resume score: 82"
}
```

---

### 6. `trigger_analysis`
Manually trigger a resume re-analysis.

**Input:**
```json
{
  "session_id": "uuid-string"
}
```

**Output:**
```json
{
  "success": true,
  "message": "Analysis triggered successfully"
}
```

---

### 7. `poll_score_until_target`
Repeatedly analyze and check score until reaching target.

**Input:**
```json
{
  "session_id": "uuid-string",
  "target_score": 95,            // default: 95
  "max_attempts": 8,             // default: 8
  "wait_between_attempts_sec": 8 // default: 8
}
```

**Output:**
```json
{
  "success": true,
  "final_score": 95,
  "target_reached": true,
  "attempts_used": 5,
  "message": "Polling complete. Final score: 95"
}
```

---

### 8. `download_tailored_resume`
Download the tailored resume as PDF.

**Input:**
```json
{
  "session_id": "uuid-string",
  "output_dir": "/path/to/downloads"  // optional, defaults to "."
}
```

**Output:**
```json
{
  "success": true,
  "file_path": "/path/to/downloads/tailored_resume_20260529_190000.pdf",
  "message": "Resume downloaded: /path/to/downloads/tailored_resume_20260529_190000.pdf"
}
```

---

### 9. `tailor_and_download`
Run the full ResumeUp-only pipeline in one call: authenticate, upload/open resume, enter job description, improve score with ResumeUp AI, and download PDF.

**Input:**
```json
{
  "job_description_text": "Full job description...",
  "resume_id": "optional-uuid",
  "file_path": "/path/to/resume.pdf",
  "target_score": 95,
  "output_dir": "."
}
```

---

### 10. `end_browser_session`
Close a browser session and clean up resources.

**Input:**
```json
{
  "session_id": "uuid-string"
}
```

**Output:**
```json
{
  "success": true,
  "message": "Session closed: uuid-string"
}
```

---

## Usage Example: Orchestrating Resume Tailoring via LLM

```python
# This is how an LLM would orchestrate the tools:

# Step 1: Start browser session
session = await llm.call_tool("start_browser_session", {
    "email": "user@example.com",
    "password": "password123"
})
session_id = session["session_id"]

# Step 2: Upload resume
resume = await llm.call_tool("upload_resume", {
    "session_id": session_id,
    "file_path": "~/Desktop/my_resume.pdf"
})

# Step 3: Parse job description
job = await llm.call_tool("parse_job_description", {
    "job_description_text": open("job_description.txt").read()
})

# Step 4: Upload job to ResumeUp
await llm.call_tool("upload_job_to_resumeup", {
    "session_id": session_id,
    "job_description_text": job.full_text
})

# Step 5: Poll until target score reached
result = await llm.call_tool("poll_score_until_target", {
    "session_id": session_id,
    "target_score": 95,
    "max_attempts": 8
})

# Step 6: Download tailored resume
download = await llm.call_tool("download_tailored_resume", {
    "session_id": session_id,
    "output_dir": "~/Downloads"
})

# Step 7: Close session
await llm.call_tool("end_browser_session", {
    "session_id": session_id
})
```

---

## Project Structure

```
resume-mcp-server/
├── mcp_server.py              # Main MCP server & tool handlers
├── resume_processor.py        # Playwright browser initialization & auth
├── resumeup_tools.py          # ResumeUp.ai interaction handlers
├── job_parser.py              # Job description parsing utilities
├── session_manager.py         # Browser session lifecycle management
├── utils.py                   # Common utility functions
├── models.py                  # Data models (dataclasses)
├── constants.py               # Project constants & patterns
├── requirements.txt           # Python dependencies
├── .env.example               # Environment configuration template
├── tests/                     # Unit & integration tests
├── README.md                  # This file
└── examples/                  # Sample files
```

---

## Configuration

Create `.env` file with:

```bash
# ResumeUp Credentials
RESUMEUP_EMAIL=your-email@example.com
RESUMEUP_PASSWORD=your-password

# Session Configuration
RESUMEUP_SESSION_DIR=~/.resumeup_automation
RESUMEUP_HEADLESS=false

# MCP Server Configuration
MCP_TIMEOUT=120
MCP_PORT=8000
```

---

## Running the Server

### As a stdio-based MCP server:

```bash
python mcp_server.py
```

The server reads JSON-formatted requests from stdin and writes responses to stdout.

### Example stdin request:

```json
{"tool": "start_browser_session", "params": {"email": "user@example.com", "password": "password123"}}
```

### Response:

```json
{"success": true, "session_id": "abc123...", "is_logged_in": true, "message": "Browser session started and authenticated"}
```

---

## Testing

Run unit tests:

```bash
pytest tests/ -v
```

Run with coverage:

```bash
pytest tests/ --cov=. --cov-report=html
```

---

## Architecture

### Session Management
- Each user gets a unique `session_id` (UUID)
- Sessions maintain Playwright browser context & page objects
- Persistent session directory stores authentication cookies
- Sessions auto-cleanup after 24 hours of inactivity

### Tool Handlers
1. **Resume Processor**: Handles browser init, auth, template selection
2. **ResumeUp Handler**: Direct Playwright interactions with ResumeUp.ai
3. **Job Parser**: Regex-based extraction of job requirements (no browser)
4. **Session Manager**: Global session lifecycle tracking

### Data Flow
```
LLM Request
    ↓
MCP Server receives tool call
    ↓
Route to appropriate handler
    ↓
Handler executes (may use Playwright)
    ↓
Update session state
    ↓
Return JSON response to LLM
```

---

## Common Workflows

### Workflow 1: Full Automation (Upload → Tailor → Download)

```bash
# 1. Start session
curl -X POST http://localhost:8000/call \
  -H "Content-Type: application/json" \
  -d '{"tool": "start_browser_session", "params": {"email": "user@example.com", "password": "pass123"}}'

# 2. Upload resume
curl -X POST http://localhost:8000/call \
  -H "Content-Type: application/json" \
  -d '{"tool": "upload_resume", "params": {"session_id": "SESSION_ID", "file_path": "resume.pdf"}}'

# 3. Parse and upload job
curl -X POST http://localhost:8000/call \
  -H "Content-Type: application/json" \
  -d '{"tool": "parse_job_description", "params": {"job_description_text": "JOB TEXT"}}'

# 4. Poll until target score
curl -X POST http://localhost:8000/call \
  -H "Content-Type: application/json" \
  -d '{"tool": "poll_score_until_target", "params": {"session_id": "SESSION_ID", "target_score": 95}}'

# 5. Download result
curl -X POST http://localhost:8000/call \
  -H "Content-Type: application/json" \
  -d '{"tool": "download_tailored_resume", "params": {"session_id": "SESSION_ID", "output_dir": "."}}'
```

### Workflow 2: Reuse Existing Resume

```python
# Use existing resume by ID instead of uploading new file
{
  "tool": "upload_resume",
  "params": {
    "session_id": "SESSION_ID",
    "resume_id": "existing-resumeup-uuid"
  }
}
```

---

## LinkedIn Job Search & Apply Workflow

This server can search LinkedIn jobs, tailor your resume for each match via ResumeUp, and queue applications for Easy Apply.

### Setup

Add LinkedIn settings to `.env` (manual login is supported if credentials are omitted):

```bash
LINKEDIN_EMAIL=your-email@example.com
LINKEDIN_PASSWORD=your-password
PROFILE_SKILLS=AWS,Python,Kubernetes,Security
APPLICATIONS_OUTPUT_DIR=~/applications
```

On first run, a browser window opens for LinkedIn login. Sessions persist in `~/.linkedin_automation/`.

### End-to-end workflow

```
1. search_and_tailor       → Find Easy Apply jobs, tailor resumes, save to review queue
2. get_application_history → Review tailored jobs (status: tailored)
3. approve_application     → Mark jobs you want to apply to
4. linkedin_easy_apply     → Pre-fill Easy Apply (submit=false by default)
5. linkedin_easy_apply     → Submit after review (submit=true, require_approval=false)
```

### Example: search and tailor

```json
{
  "keywords": "security architect",
  "location": "Remote",
  "easy_apply_only": true,
  "limit": 5,
  "min_match_score": 0.3,
  "file_path": "/path/to/base-resume.pdf",
  "target_score": 95
}
```

Each tailored job is saved under `~/applications/<job_id>-<company>/` with:
- `job_description.txt`
- Tailored resume PDF

Application records are stored in `~/.resumeup_automation/applications.json`.

### LinkedIn MCP tools

| Tool | Description |
|------|-------------|
| `linkedin_search_jobs` | Search LinkedIn and return job listings |
| `linkedin_get_job_details` | Scrape full job description from a URL |
| `search_and_tailor` | Search → match → tailor → queue (main pipeline) |
| `get_application_history` | List applications by status |
| `approve_application` | Mark application ready for Easy Apply |
| `linkedin_easy_apply` | Pre-fill or submit Easy Apply for a queued job |

### Application statuses

| Status | Meaning |
|--------|---------|
| `discovered` | Job found, not yet processed |
| `tailoring` | ResumeUp tailoring in progress |
| `tailored` | PDF ready — review recommended |
| `approved` | Ready for Easy Apply |
| `applied` | Submitted on LinkedIn |
| `skipped` | Low match score or duplicate |
| `failed` | Scrape or tailoring error |

### Important notes

- **LinkedIn ToS**: Automated scraping and applying may violate LinkedIn's terms. Use assist mode and rate-limit applications.
- **Easy Apply varies**: Jobs with many custom screening questions are skipped by default (`max_custom_questions=3`).
- **Manual submit default**: `linkedin_easy_apply` pre-fills forms but does not submit unless `submit=true`.

---

## Error Handling

All tool responses include:
- `success`: Boolean indicating success/failure
- `message`: Human-readable message or error description
- Additional fields specific to each tool

Example error response:
```json
{
  "success": false,
  "message": "Resume file not found: /nonexistent/path.pdf"
}
```

---

## Browser Automation Notes

- **Headless Mode**: Disabled by default if manual login needed, enabled if credentials provided
- **Session Persistence**: Browser cookies saved to `~/.resumeup_automation/` for faster login on subsequent runs
- **Screenshot Debugging**: Server can take screenshots for troubleshooting
- **Timeouts**: Configurable via `MCP_TIMEOUT` environment variable (default: 120s)

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

MIT License - see LICENSE file for details

---

## Support

For issues, questions, or feedback:
- Open an issue on GitHub
- Check existing documentation in `/docs`
- Review original script: `resumeup_tailor.py` in repo history

---

## Acknowledgments

- Original automation script: `resumeup_tailor.py`
- Playwright: https://playwright.dev/python/
- ResumeUp.ai: https://resumeup.ai/
- MCP Protocol: https://modelcontextprotocol.io/

---

**Last Updated**: 2026-05-29  
**Version**: 1.1.0
