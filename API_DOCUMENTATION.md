# 📱 Job Assistant AI Agent Platform - Complete Flutter API Reference

This document serves as the comprehensive REST API specification for the **Job Assistant AI Agent Platform** backend (Modules 1 through 8). It contains all endpoint specifications, headers, request bodies, query parameters, response JSON schemas, and error definitions needed by the Flutter mobile application developer.

---

## 🌐 Base URL & Server Info

- **Base URL**: `http://<your-server-ip>:8000/api/v1` (Dev local server: `http://localhost:8000/api/v1` or `http://10.0.2.2:8000/api/v1` for Android Emulator)
- **Health Check**: `GET /health`
- **Interactive Swagger Docs**: `http://localhost:8000/docs`

---

## 🔒 Authentication & Authorization

All endpoints except public Auth endpoints (`/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/request-password-reset`, `/auth/reset-password`, `/auth/verify-email`) require HTTP Bearer token authentication:

```http
Authorization: Bearer <access_token>
```

### JWT & Refresh Token Architecture
- **Access Token**: Short-lived (15 minutes). Transmitted in the `Authorization` header.
- **Refresh Token**: High-entropy opaque string (7 days validity). Must be stored securely in Flutter (e.g., using `flutter_secure_storage`).
- **Token Rotation**: Calling `POST /api/v1/auth/refresh` invalidates the previous refresh token and returns a new access/refresh token pair.

---

## 🚨 Standard Error Envelope

All API errors strictly return the following JSON envelope format:

```json
{
  "error": {
    "code": "ERROR_CODE_STRING",
    "message": "Human readable error description",
    "details": null
  }
}
```

### Common HTTP Status & Error Codes:
- `400 Bad Request` (`BAD_REQUEST`): Invalid payload format or missing required fields.
- `401 Unauthorized` (`UNAUTHENTICATED`): Missing, expired, or invalid JWT token.
- `403 Forbidden` (`PERMISSION_DENIED`): Resource belongs to another tenant/user.
- `404 Not Found` (`NOT_FOUND`): Resource ID does not exist.
- `409 Conflict` (`ALREADY_EXISTS` / `CONFLICT`): Skill or project already exists / attached.
- `422 Unprocessable Entity` (`VALIDATION_ERROR`): Pydantic input validation failure (`details` contains array of invalid fields).
- `429 Too Many Requests` (`RATE_LIMIT_EXEDED` / `ACCOUNT_LOCKED`): Rate limit exceeded or account locked due to 5 consecutive failed logins (15 min lockout).
- `500 Internal Server Error` (`INTERNAL_SERVER_ERROR`): Server error.

---

# 📚 API Endpoints Overview

- [1. Authentication & User Profile](#1-authentication--user-profile)
- [2. CV Intake & Structured Storage](#2-cv-intake--structured-storage)
- [3. Profile Skills Management](#3-profile-skills-management)
- [4. Portfolio Projects Management](#4-portfolio-projects-management)
- [5. Daily Learning Log & Skill Triage](#5-daily-learning-log--skill-triage)
- [6. Job Applications, JD Parsing & Tailoring](#6-job-applications-jd-parsing--tailoring)
- [7. Interview Prep Agent](#7-interview-prep-agent)
- [8. Dashboard & Skill Gap Analytics](#8-dashboard--skill-gap-analytics)
- [9. Cover Letter Generation Agent](#9-cover-letter-generation-agent)

---

## 1. Authentication & User Profile

### 1.1 Register User
- **Method**: `POST`
- **Path**: `/api/v1/auth/register`
- **Auth**: None
- **Rate Limit**: 5 requests / min

**Request Body**:
```json
{
  "email": "user@example.com",
  "password": "Password123!"
}
```

**Response (`201 Created`)**:
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "email": "user@example.com",
  "is_verified": false,
  "created_at": "2026-09-08T12:00:00Z"
}
```

---

### 1.2 User Login
- **Method**: `POST`
- **Path**: `/api/v1/auth/login`
- **Auth**: None
- **Rate Limit**: 5 requests / min

**Request Body**:
```json
{
  "email": "user@example.com",
  "password": "Password123!"
}
```

**Response (`200 OK`)**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1Ni...",
  "refresh_token": "4f8a9e7b2c...",
  "token_type": "bearer",
  "expires_in": 900
}
```

---

### 1.3 Refresh Tokens
- **Method**: `POST`
- **Path**: `/api/v1/auth/refresh`
- **Auth**: None
- **Rate Limit**: 10 requests / min

**Request Body**:
```json
{
  "refresh_token": "4f8a9e7b2c..."
}
```

**Response (`200 OK`)**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1Ni...",
  "refresh_token": "new_opaque_refresh_token_string...",
  "token_type": "bearer",
  "expires_in": 900
}
```

---

### 1.4 Logout
- **Method**: `POST`
- **Path**: `/api/v1/auth/logout`
- **Auth**: None

**Request Body**:
```json
{
  "refresh_token": "4f8a9e7b2c..."
}
```

**Response (`200 OK`)**:
```json
{
  "message": "Successfully logged out."
}
```

---

### 1.5 Get Current User Profile
- **Method**: `GET`
- **Path**: `/api/v1/auth/me`
- **Auth**: Bearer Token Required

**Response (`200 OK`)**:
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "email": "user@example.com",
  "is_verified": true,
  "created_at": "2026-09-08T12:00:00Z"
}
```

---

## 2. CV Intake & Structured Storage

### 2.1 Upload CV File
- **Method**: `POST`
- **Path**: `/api/v1/cvs/upload`
- **Auth**: Bearer Token Required
- **Content-Type**: `multipart/form-data`
- **File Limits**: PDF, DOCX, or TXT (Max 10MB)

**Form Fields**:
- `file`: (Binary file data)

**Response (`201 Created`)**:
```json
{
  "cv_id": "8f3b2a11-1234-5678-9abc-def012345678",
  "message": "CV uploaded and parsed successfully.",
  "is_canonical": false,
  "parse_confidence": "high",
  "parsing_notes": [],
  "parsed_data": {
    "contact_info": {
      "full_name": "Jane Doe",
      "email": "jane@example.com",
      "phone": "+1-555-0188",
      "location": "San Francisco, CA",
      "summary": "Experienced Full Stack Software Engineer."
    },
    "work_history": [
      {
        "id": "11111111-1111-1111-1111-111111111111",
        "company": "Acme Corp",
        "role": "Senior Engineer",
        "location": "San Francisco, CA",
        "start_date": "2021-01",
        "end_date": null,
        "is_current": true,
        "description": "Architected async Python backend microservices."
      }
    ],
    "education": [
      {
        "id": "22222222-2222-2222-2222-222222222222",
        "institution": "Stanford University",
        "degree": "B.S.",
        "field_of_study": "Computer Science",
        "start_date": "2016",
        "end_date": "2020"
      }
    ],
    "skills": ["Python", "FastAPI", "PostgreSQL", "Docker"],
    "parse_confidence": "high",
    "parsing_notes": []
  }
}
```

---

### 2.2 Get Active User CV
- **Method**: `GET`
- **Path**: `/api/v1/cvs/me`
- **Auth**: Bearer Token Required

**Response (`200 OK`)**:
```json
{
  "id": "8f3b2a11-1234-5678-9abc-def012345678",
  "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "title": "Jane Doe's CV",
  "variant_name": "Canonical Baseline",
  "is_canonical": true,
  "raw_file_name": "jane_resume.pdf",
  "mime_type": "application/pdf",
  "file_size": 245000,
  "full_name": "Jane Doe",
  "email": "jane@example.com",
  "phone": "+1-555-0188",
  "location": "San Francisco, CA",
  "summary": "Experienced Full Stack Software Engineer.",
  "parse_confidence": "high",
  "work_histories": [
    {
      "id": "11111111-1111-1111-1111-111111111111",
      "company": "Acme Corp",
      "role": "Senior Engineer",
      "location": "San Francisco, CA",
      "start_date": "2021-01",
      "end_date": null,
      "is_current": true,
      "description": "Architected async Python backend microservices."
    }
  ],
  "education_entries": [
    {
      "id": "22222222-2222-2222-2222-222222222222",
      "institution": "Stanford University",
      "degree": "B.S.",
      "field_of_study": "Computer Science",
      "start_date": "2016",
      "end_date": "2020"
    }
  ],
  "skills": [
    {
      "id": "33333333-3333-3333-3333-333333333333",
      "name": "Python",
      "category": "language"
    }
  ],
  "created_at": "2026-09-08T12:00:00Z",
  "updated_at": "2026-09-08T12:05:00Z"
}
```

---

### 2.3 Edit CV Draft
- **Method**: `PUT`
- **Path**: `/api/v1/cvs/draft`
- **Auth**: Bearer Token Required

**Request Body**:
```json
{
  "full_name": "Jane M. Doe",
  "summary": "Updated executive summary for Flutter app...",
  "work_history": [
    {
      "company": "Acme Corp",
      "role": "Lead Backend Architect",
      "is_current": true,
      "description": "Updated description..."
    }
  ]
}
```

**Response (`200 OK`)**: Same schema as `GET /api/v1/cvs/me`.

---

### 2.4 Finalize CV Baseline
- **Method**: `POST`
- **Path**: `/api/v1/cvs/finalize`
- **Auth**: Bearer Token Required

**Response (`200 OK`)**: Returns CV object with `is_canonical: true`.

---

### 2.5 Download Original Raw CV File
- **Method**: `GET`
- **Path**: `/api/v1/cvs/raw`
- **Auth**: Bearer Token Required
- **Response**: Binary stream (`application/pdf`, `application/vnd.openxmlformats-officedocument.wordprocessingml.document`, or `text/plain`). Includes header `Content-Disposition: attachment; filename="<original_name>"`.

---

### 2.6 Delete User CV Baseline
- **Method**: `DELETE`
- **Path**: `/api/v1/cvs/me`
- **Auth**: Bearer Token Required
- **Response**: `204 No Content`

---

## 3. Profile Skills Management

### 3.1 List Profile Skills
- **Method**: `GET`
- **Path**: `/api/v1/skills`
- **Auth**: Bearer Token Required

**Response (`200 OK`)**:
```json
[
  {
    "id": "44444444-4444-4444-4444-444444444444",
    "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "name": "Flutter",
    "name_slug": "flutter",
    "category": "framework",
    "proficiency": 4,
    "source": "manual",
    "created_at": "2026-09-08T12:00:00Z",
    "updated_at": "2026-09-08T12:00:00Z"
  }
]
```

---

### 3.2 Create Profile Skill
- **Method**: `POST`
- **Path**: `/api/v1/skills`
- **Auth**: Bearer Token Required

**Request Body**:
```json
{
  "name": "Dart",
  "category": "language",
  "proficiency": 4,
  "source": "manual"
}
```

**Response (`201 Created`)**: Returns `SkillResponse` object. Returns `409 Conflict` if duplicate slug exists.

---

### 3.3 Update Profile Skill
- **Method**: `PUT`
- **Path**: `/api/v1/skills/{skill_id}`
- **Auth**: Bearer Token Required

**Request Body**:
```json
{
  "proficiency": 5,
  "category": "core_language"
}
```

**Response (`200 OK`)**: Returns updated `SkillResponse` object.

---

### 3.4 Delete Profile Skill
- **Method**: `DELETE`
- **Path**: `/api/v1/skills/{skill_id}`
- **Auth**: Bearer Token Required
- **Response**: `204 No Content`

---

## 4. Portfolio Projects Management

### 4.1 List Portfolio Projects
- **Method**: `GET`
- **Path**: `/api/v1/projects`
- **Auth**: Bearer Token Required

**Response (`200 OK`)**:
```json
[
  {
    "id": "55555555-5555-5555-5555-555555555555",
    "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
    "title": "E-Commerce App in Flutter",
    "description": "Cross-platform mobile client with clean architecture.",
    "urls": [
      {
        "label": "GitHub",
        "url": "https://github.com/example/flutter-shop"
      }
    ],
    "start_date": "2024-01",
    "end_date": "2024-06",
    "is_ongoing": false,
    "skills": [
      {
        "id": "44444444-4444-4444-4444-444444444444",
        "name": "Flutter",
        "name_slug": "flutter",
        "category": "framework",
        "proficiency": 4
      }
    ],
    "created_at": "2026-09-08T12:00:00Z",
    "updated_at": "2026-09-08T12:00:00Z"
  }
]
```

---

### 4.2 Create Portfolio Project
- **Method**: `POST`
- **Path**: `/api/v1/projects`
- **Auth**: Bearer Token Required

**Request Body**:
```json
{
  "title": "ShopLedger Mobile",
  "description": "Offline-first accounting mobile app built with Flutter and SQLite.",
  "urls": [
    {
      "label": "GitHub Repo",
      "url": "https://github.com/example/shopledger"
    }
  ],
  "start_date": "2025-01",
  "is_ongoing": true
}
```

**Response (`201 Created`)**: Returns `ProjectResponse` object.

---

### 4.3 Attach Skill to Project
- **Method**: `POST`
- **Path**: `/api/v1/projects/{project_id}/skills/{skill_id}`
- **Auth**: Bearer Token Required

**Response (`200 OK`)**: Returns updated `ProjectResponse` object with embedded skills list.

---

### 4.4 Detach Skill from Project
- **Method**: `DELETE`
- **Path**: `/api/v1/projects/{project_id}/skills/{skill_id}`
- **Auth**: Bearer Token Required

**Response (`200 OK`)**: Returns updated `ProjectResponse` object.

---

## 5. Daily Learning Log & Skill Triage

### 5.1 Post Daily Learning Entry
- **Method**: `POST`
- **Path**: `/api/v1/learning`
- **Auth**: Bearer Token Required

**Request Body**:
```json
{
  "title": "Studied Flutter BLoC State Management",
  "content": "Built a sample app implementing BLoC pattern with hydrated_bloc for local storage persistence.",
  "timestamp": "2026-09-08T14:00:00Z"
}
```

**Response (`201 Created`)**:
```json
{
  "id": "66666666-6666-6666-6666-666666666666",
  "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "title": "Studied Flutter BLoC State Management",
  "content": "Built a sample app implementing BLoC pattern with hydrated_bloc for local storage persistence.",
  "timestamp": "2026-09-08T14:00:00Z",
  "created_at": "2026-09-08T14:00:01Z",
  "updated_at": "2026-09-08T14:00:01Z"
}
```

---

### 5.2 List Pending Skill Proposals
- **Method**: `GET`
- **Path**: `/api/v1/learning/proposals/pending`
- **Auth**: Bearer Token Required

**Response (`200 OK`)**:
```json
[
  {
    "id": "77777777-7777-7777-7777-777777777777",
    "entry_id": "66666666-6666-6666-6666-666666666666",
    "is_skill_worthy": true,
    "reasoning": "Detected new learning content relating to Flutter state management.",
    "status": "pending",
    "proposed_skills": [
      {
        "id": "88888888-8888-8888-8888-888888888888",
        "proposal_id": "77777777-7777-7777-7777-777777777777",
        "skill_name": "BLoC",
        "action": "create_new",
        "matched_skill_id": null,
        "confidence": "high",
        "status": "pending"
      }
    ],
    "created_at": "2026-09-08T14:00:05Z",
    "updated_at": "2026-09-08T14:00:05Z"
  }
]
```

---

### 5.3 Approve Skill Proposal
- **Method**: `POST`
- **Path**: `/api/v1/learning/proposals/{proposal_id}/approve`
- **Auth**: Bearer Token Required

**Request Body**:
```json
{
  "approved_item_ids": [
    "88888888-8888-8888-8888-888888888888"
  ]
}
```

**Response (`200 OK`)**: Returns updated proposal response with status `"approved"`. Updates canonical skills table automatically.

---

## 6. Job Applications, JD Parsing & Tailoring

### 6.1 Submit Job Description
- **Method**: `POST`
- **Path**: `/api/v1/applications`
- **Auth**: Bearer Token Required

**Request Body**:
```json
{
  "job_title": "Senior Flutter Developer",
  "company": "TechCorp Inc.",
  "jd_raw_text": "We are seeking a Senior Flutter Developer with expertise in Dart, REST APIs, GraphQL, and Firebase. You will architect mobile solutions and write unit/widget tests.",
  "source_url": "https://techcorp.com/careers/flutter-dev"
}
```

**Response (`201 Created`)**:
```json
{
  "id": "99999999-9999-9999-9999-999999999999",
  "user_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "job_title": "Senior Flutter Developer",
  "company": "TechCorp Inc.",
  "source_url": "https://techcorp.com/careers/flutter-dev",
  "status": "draft",
  "parse_status": "parsed",
  "requirements": [
    {
      "id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      "skill_name": "Flutter",
      "skill_slug": "flutter",
      "is_required": true,
      "seniority": "senior"
    },
    {
      "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
      "skill_name": "GraphQL",
      "skill_slug": "graphql",
      "is_required": false,
      "seniority": null
    }
  ],
  "created_at": "2026-09-08T15:00:00Z",
  "updated_at": "2026-09-08T15:00:00Z"
}
```

---

### 6.2 Get Application Match Report
- **Method**: `GET`
- **Path**: `/api/v1/applications/{app_id}/match`
- **Auth**: Bearer Token Required

**Response (`200 OK`)**:
```json
{
  "skill_matches": [
    {
      "jd_skill_name": "Flutter",
      "jd_skill_slug": "flutter",
      "match_status": "matched",
      "matched_skill_id": "44444444-4444-4444-4444-444444444444",
      "matched_skill_name": "Flutter",
      "user_proficiency": 4,
      "is_required": true
    },
    {
      "jd_skill_name": "GraphQL",
      "jd_skill_slug": "graphql",
      "match_status": "missing",
      "matched_skill_id": null,
      "matched_skill_name": null,
      "user_proficiency": null,
      "is_required": false
    }
  ],
  "project_rankings": [
    {
      "project_id": "55555555-5555-5555-5555-555555555555",
      "project_title": "E-Commerce App in Flutter",
      "matched_skill_count": 2,
      "total_jd_skills": 4,
      "relevance_score": 0.5,
      "matched_skill_names": ["Flutter", "Dart"]
    }
  ],
  "overall_match_score": 0.85,
  "missing_required_count": 0,
  "matched_required_count": 3
}
```

---

### 6.3 Generate Tailored CV Draft
- **Method**: `POST`
- **Path**: `/api/v1/applications/{app_id}/tailor`
- **Auth**: Bearer Token Required

**Response (`201 Created`)**:
```json
{
  "id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
  "job_application_id": "99999999-9999-9999-9999-999999999999",
  "source_cv_id": "8f3b2a11-1234-5678-9abc-def012345678",
  "tailored_content": "Tailored executive summary highlighting Flutter and Dart architecture...",
  "diff_summary": "Reordered work history experience bullets; prioritized mobile accomplishments; highlighted ShopLedger project.",
  "status": "draft",
  "selected_project_ids": ["55555555-5555-5555-5555-555555555555"],
  "created_at": "2026-09-08T15:05:00Z",
  "updated_at": "2026-09-08T15:05:00Z"
}
```

---

### 6.4 Finalize Tailored CV
- **Method**: `POST`
- **Path**: `/api/v1/applications/{app_id}/tailor/finalize`
- **Auth**: Bearer Token Required

**Response (`200 OK`)**: Returns `TailoredCVResponse` object with `status: "finalized"`.

---

## 7. Interview Prep Agent

### 7.1 Generate Interview Prep Set
- **Method**: `POST`
- **Path**: `/api/v1/applications/{app_id}/interview-prep`
- **Auth**: Bearer Token Required

**Response (`201 Created`)**:
```json
{
  "id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
  "job_application_id": "99999999-9999-9999-9999-999999999999",
  "status": "generated",
  "generated_at": "2026-09-08T15:10:00Z",
  "questions": [
    {
      "id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
      "prep_set_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
      "question_text": "How do you handle asynchronous state and error boundaries in Flutter using BLoC?",
      "category": "technical",
      "rationale": "Required by Senior Flutter Developer JD and matches your matched skill 'Flutter'.",
      "suggested_answer_outline": "Focus on BlocObserver, BlocListener, and handling failure state classes.",
      "user_notes": null,
      "is_practiced": false,
      "ordering": 1
    },
    {
      "id": "ffffffff-ffff-ffff-ffff-ffffffffffff",
      "prep_set_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
      "question_text": "Walk me through the local caching architecture of your E-Commerce App in Flutter project.",
      "category": "project",
      "rationale": "Directly references your shortlisted project 'E-Commerce App in Flutter'.",
      "suggested_answer_outline": "Explain SQLite schema, offline sync queue, and conflict resolution strategy.",
      "user_notes": null,
      "is_practiced": false,
      "ordering": 2
    }
  ]
}
```

---

### 7.2 Practice & Note Interview Question
- **Method**: `PUT`
- **Path**: `/api/v1/applications/{app_id}/interview-prep/questions/{question_id}`
- **Auth**: Bearer Token Required

**Request Body**:
```json
{
  "user_notes": "Mention my experience with hydrated_bloc for state restoration.",
  "is_practiced": true
}
```

**Response (`200 OK`)**: Returns updated `InterviewQuestionResponse` object.

---

## 8. Dashboard & Skill Gap Analytics

### 8.1 List Dashboard Job Applications
- **Method**: `GET`
- **Path**: `/api/v1/dashboard/applications`
- **Query Params**:
  - `status` (optional): `draft`, `tailored`, or `applied`
- **Auth**: Bearer Token Required

**Response (`200 OK`)**:
```json
{
  "items": [
    {
      "id": "99999999-9999-9999-9999-999999999999",
      "job_title": "Senior Flutter Developer",
      "company": "TechCorp Inc.",
      "status": "tailored",
      "parse_status": "parsed",
      "matched_skills_count": 3,
      "required_skills_count": 4,
      "created_at": "2026-09-08T15:00:00Z",
      "updated_at": "2026-09-08T15:05:00Z"
    }
  ]
}
```

---

### 8.2 Get Application Aggregated Detail View
- **Method**: `GET`
- **Path**: `/api/v1/dashboard/applications/{app_id}`
- **Auth**: Bearer Token Required

**Response (`200 OK`)**: Aggregates Application details, parsed requirements, skill matches, tailored CV draft, and interview prep questions in a single JSON payload.

```json
{
  "application": { ... },
  "skill_matches": [ ... ],
  "tailored_cv": { ... },
  "interview_prep": { ... }
}
```

---

### 8.3 Get Skill Gap Analytics Report
- **Method**: `GET`
- **Path**: `/api/v1/dashboard/analytics/skill-gaps`
- **Auth**: Bearer Token Required

**Response (`200 OK`)**:
```json
{
  "top_missing_skills": [
    {
      "skill_slug": "graphql",
      "skill_name": "GraphQL",
      "frequency_count": 4
    }
  ],
  "top_matched_skills": [
    {
      "skill_slug": "flutter",
      "skill_name": "Flutter",
      "frequency_count": 8
    }
  ],
  "learning_nudge": "You've had 'GraphQL' flagged as a missing requirement in 4 job applications. Consider logging a learning progress entry for it!"
}
```

---

## 9. Cover Letter Generation Agent

### 9.1 Generate Cover Letter
- **Method**: `POST`
- **Path**: `/api/v1/applications/{app_id}/cover-letter`
- **Auth**: Bearer Token Required

**Request Body**:
```json
{
  "tone": "conversational",
  "length": "standard"
}
```
*Note: Valid `tone` choices: `formal`, `conversational`. Valid `length` choices: `short`, `standard`.*

**Response (`201 Created`)**:
```json
{
  "id": "12121212-1212-1212-1212-121212121212",
  "job_application_id": "99999999-9999-9999-9999-999999999999",
  "content": "Dear Hiring Manager at TechCorp Inc.,\n\nI am writing to express my enthusiastic interest in the Senior Flutter Developer role...",
  "tone": "conversational",
  "length": "standard",
  "status": "draft",
  "unverified_claims": null,
  "created_at": "2026-09-08T16:00:00Z",
  "updated_at": "2026-09-08T16:00:00Z"
}
```

---

### 9.2 Edit Cover Letter Content Inline
- **Method**: `PUT`
- **Path**: `/api/v1/applications/{app_id}/cover-letter`
- **Auth**: Bearer Token Required

**Request Body**:
```json
{
  "content": "Updated letter text with custom opening paragraph..."
}
```

**Response (`200 OK`)**: Returns updated `CoverLetterResponse` object.

---

### 9.3 Finalize Cover Letter
- **Method**: `POST`
- **Path**: `/api/v1/applications/{app_id}/cover-letter/finalize`
- **Auth**: Bearer Token Required

**Response (`200 OK`)**: Returns `CoverLetterResponse` with `status: "finalized"`.

---

### 9.4 Export Cover Letter
- **Method**: `GET`
- **Path**: `/api/v1/applications/{app_id}/cover-letter/export`
- **Auth**: Bearer Token Required
- **Response**: `text/plain` file download (`Content-Disposition: attachment; filename="cover_letter_<app_id>.txt"`).
