# Security Specification & Threat Model

## 1. Data Invariants
- Each user can only read and write their own UserProfile (`/users/{userId}` where `userId == request.auth.uid`).
- StudyPlans (`/study_plans/{planId}`) must belong to the authenticated user (`resource.data.userId == request.auth.uid`).
- MainsEvaluations (`/evaluations/{evalId}`) must be owned by the user submitting them (`userId == request.auth.uid`).
- CourseEnrollments (`/enrollments/{enrollmentId}`) must be owned by the enrolled user (`userId == request.auth.uid`).
- Catch-all default deny for all unmatched paths.

## 2. The Dirty Dozen Payloads
1. Injecting arbitrary admin role in `/users/{userId}`: Blocked because role updates are restricted.
2. Cross-user reading of another aspirant's profile: Blocked by `request.auth.uid == userId`.
3. Reading another user's study plans: Blocked by `resource.data.userId == request.auth.uid`.
4. Updating another user's study plan: Blocked by `resource.data.userId == request.auth.uid`.
5. Deleting someone else's study plan or answer evaluation: Blocked by ownership verification.
6. Spoofing `userId` on creation of study plan: Blocked by `request.resource.data.userId == request.auth.uid`.
7. Submitting oversized payloads (>10KB): Blocked by string length guards.
8. Modifying immutable field `id` or `userId` in study plan: Blocked by immutability rules.
9. Malformed ID poisoning: Blocked by `isValidId(id)`.
10. Blanket unauthenticated access: Blocked by `isSignedIn()`.
11. Unauthenticated query scraping: Blocked by list rule requiring `resource.data.userId == request.auth.uid`.
12. Creating orphaned records without required fields: Blocked by `isValidEntity()` schema checks.
