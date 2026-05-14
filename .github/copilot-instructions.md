# Copilot Code Review Instructions

## 🔐 Security (Highest Priority)
- Flag any hardcoded secrets, API keys, tokens, or passwords
- Check for SQL injection, XSS, CSRF, and command injection vulnerabilities
- Verify all user inputs are validated and sanitized before use
- Ensure sensitive data is never logged or exposed in error messages
- Check that authentication and authorization are enforced on every endpoint
- Flag use of outdated or vulnerable dependencies
- Verify HTTPS is enforced and no mixed content issues exist
- Check for insecure deserialization or unsafe use of eval/exec
- Ensure JWT tokens, sessions, and cookies are handled securely
- Flag any broken access control (e.g. user can access another user's data)

## ⚡ Performance
- Identify N+1 query problems in database calls
- Flag unnecessary re-renders in frontend components
- Check for missing indexes on frequently queried database fields
- Warn about synchronous blocking operations that should be async
- Flag loading large datasets into memory without pagination or streaming
- Identify redundant API calls that could be cached or batched
- Check for memory leaks (e.g. unremoved event listeners, unclosed connections)
- Warn about large bundle sizes or missing lazy loading in frontend code
- Flag expensive operations running inside loops
- Check that heavy computations are memoized or moved off the main thread

## 🧪 Test Coverage
- Flag any new function, class, or module with no corresponding test
- Check that edge cases are covered (null, empty, boundary values)
- Warn if error/exception paths are untested
- Verify that mocks and stubs are used correctly and not hiding real bugs
- Check that tests have meaningful assertions, not just that code runs
- Flag tests that are tightly coupled to implementation details
- Ensure async code is properly awaited in tests
- Warn about skipped or commented-out tests without explanation
- Check that critical business logic has both unit and integration tests
- Flag test files with no clear structure (Arrange / Act / Assert)

## 🧹 Code Quality (General)
- Flag functions longer than 40 lines — suggest breaking them up
- Warn about deeply nested code (more than 3 levels) — suggest early returns
- Check that variable and function names are descriptive and clear
- Flag duplicate code that could be extracted into a shared utility
- Ensure error handling is present and not silently swallowed
- Warn about TODO/FIXME comments left in production code
- Check that public functions and APIs have documentation/comments
- Flag dead code or unused imports/variables
- Ensure consistent formatting and code style across the file
- Check that constants are used instead of magic numbers or strings

## 🌐 API & Backend Specific
- Verify all API responses use consistent structure and status codes
- Check that pagination is implemented for list endpoints
- Flag missing rate limiting on public endpoints
- Ensure database transactions are used where atomicity is needed
- Check that background jobs handle failures and retries gracefully

## 🖥️ Frontend Specific
- Check for accessibility issues (missing alt text, ARIA labels, keyboard nav)
- Flag hardcoded colors or styles that should use design tokens/variables
- Warn about direct DOM manipulation when a framework abstraction exists
- Check that loading, error, and empty states are handled in UI components
- Flag any sensitive data stored in localStorage or sessionStorage

## 📱 Mobile Specific
- Check that offline states and network failures are handled gracefully
- Flag missing platform-specific permissions handling (iOS/Android)
- Warn about blocking the UI thread with heavy computations
- Check that deep links and navigation edge cases are handled

## 📋 Final Checklist for Every PR
- Does this change have a clear, single purpose?
- Are breaking changes documented?
- Are environment-specific configs handled via env variables?
- Is there any code that could cause issues in production but not in dev?
- Does this PR introduce any new technical debt without justification?
