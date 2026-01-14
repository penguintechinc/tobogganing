# Testing Standards

Part of [Development Standards](../STANDARDS.md)

## Testing Requirements

### Unit Testing

**All applications MUST have comprehensive unit tests:**

- **Network isolation**: Unit tests must NOT require external network connections
- **No external dependencies**: Cannot reach databases, APIs, or external services
- **Use mocks/stubs**: Mock all external dependencies and I/O operations
- **KISS principle**: Keep unit tests simple, focused, and fast
- **Test isolation**: Each test should be independent and repeatable
- **Fast execution**: Unit tests should complete in milliseconds

### Integration Testing

- Test component interactions
- Use test databases and services
- Verify API contracts
- Test authentication and authorization

### End-to-End Testing

- Test critical user workflows
- Use staging environment
- Verify full system integration

### Performance Testing

- Benchmark critical operations
- Load testing for scalability
- Regression testing for performance
