// Package validation provides PyDAL-style input validators for Go applications.
//
// This package implements validators that follow a consistent pattern:
//   - Each validator returns a ValidationResult with success/failure status
//   - Validators can be chained using the Chain function
//   - Error messages are human-readable for API responses
//
// Example usage:
//
//	chain := validation.Chain(
//	    validation.NotEmpty(),
//	    validation.Length(3, 255),
//	    validation.Email(),
//	)
//	result := chain.Validate(email)
//	if !result.IsValid {
//	    return fmt.Errorf("validation failed: %s", result.Error)
//	}
package validation

import "fmt"

// ValidationResult holds the result of a validation operation.
type ValidationResult struct {
	// IsValid indicates whether the validation passed
	IsValid bool
	// Value is the validated (possibly transformed) value
	Value any
	// Error is the error message if validation failed
	Error string
}

// Success creates a successful validation result.
func Success(value any) ValidationResult {
	return ValidationResult{
		IsValid: true,
		Value:   value,
		Error:   "",
	}
}

// Failure creates a failed validation result.
func Failure(err string) ValidationResult {
	return ValidationResult{
		IsValid: false,
		Value:   nil,
		Error:   err,
	}
}

// Failuref creates a failed validation result with formatted error.
func Failuref(format string, args ...any) ValidationResult {
	return Failure(fmt.Sprintf(format, args...))
}

// Unwrap returns the value or panics if validation failed.
func (r ValidationResult) Unwrap() any {
	if !r.IsValid {
		panic(fmt.Sprintf("validation failed: %s", r.Error))
	}
	return r.Value
}

// UnwrapOr returns the value or a default if validation failed.
func (r ValidationResult) UnwrapOr(defaultValue any) any {
	if r.IsValid {
		return r.Value
	}
	return defaultValue
}

// UnwrapString returns the value as a string or panics.
func (r ValidationResult) UnwrapString() string {
	v := r.Unwrap()
	if s, ok := v.(string); ok {
		return s
	}
	panic("value is not a string")
}

// UnwrapInt returns the value as an int or panics.
func (r ValidationResult) UnwrapInt() int {
	v := r.Unwrap()
	if i, ok := v.(int); ok {
		return i
	}
	panic("value is not an int")
}

// UnwrapFloat returns the value as a float64 or panics.
func (r ValidationResult) UnwrapFloat() float64 {
	v := r.Unwrap()
	if f, ok := v.(float64); ok {
		return f
	}
	panic("value is not a float64")
}

// Validator is the interface that all validators must implement.
type Validator interface {
	// Validate performs validation on the input value.
	Validate(value any) ValidationResult
}

// ValidatorFunc is a function type that implements Validator.
type ValidatorFunc func(value any) ValidationResult

// Validate implements the Validator interface.
func (f ValidatorFunc) Validate(value any) ValidationResult {
	return f(value)
}

// ChainedValidator chains multiple validators together.
type ChainedValidator struct {
	validators []Validator
}

// Chain creates a new ChainedValidator from multiple validators.
// Validators are run in sequence. If any validator fails,
// the chain stops and returns the failure result.
func Chain(validators ...Validator) *ChainedValidator {
	return &ChainedValidator{validators: validators}
}

// Validate runs all validators in sequence.
func (c *ChainedValidator) Validate(value any) ValidationResult {
	currentValue := value

	for _, v := range c.validators {
		result := v.Validate(currentValue)
		if !result.IsValid {
			return result
		}
		currentValue = result.Value
	}

	return Success(currentValue)
}

// Add appends a validator to the chain.
func (c *ChainedValidator) Add(v Validator) *ChainedValidator {
	c.validators = append(c.validators, v)
	return c
}

// ValidationError is a custom error type for validation failures.
type ValidationError struct {
	Field   string
	Message string
}

// Error implements the error interface.
func (e ValidationError) Error() string {
	if e.Field != "" {
		return fmt.Sprintf("%s: %s", e.Field, e.Message)
	}
	return e.Message
}

// NewValidationError creates a new ValidationError.
func NewValidationError(field, message string) ValidationError {
	return ValidationError{Field: field, Message: message}
}
