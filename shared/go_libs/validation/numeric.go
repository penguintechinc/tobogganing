package validation

import (
	"strconv"
	"strings"
)

// Int validates that a value is or can be converted to an integer.
func Int(opts ...func(*intOpts)) Validator {
	o := &intOpts{
		errorMessage: "value must be an integer",
	}
	for _, opt := range opts {
		opt(o)
	}

	return ValidatorFunc(func(value any) ValidationResult {
		switch v := value.(type) {
		case int:
			return Success(v)
		case int32:
			return Success(int(v))
		case int64:
			return Success(int(v))
		case float64:
			if v == float64(int(v)) {
				return Success(int(v))
			}
			return Failure(o.errorMessage)
		case float32:
			if v == float32(int(v)) {
				return Success(int(v))
			}
			return Failure(o.errorMessage)
		case string:
			// Don't allow floats in string form
			if strings.Contains(v, ".") || strings.ContainsAny(strings.ToLower(v), "e") {
				return Failure(o.errorMessage)
			}
			i, err := strconv.Atoi(v)
			if err != nil {
				return Failure(o.errorMessage)
			}
			return Success(i)
		default:
			return Failure(o.errorMessage)
		}
	})
}

type intOpts struct {
	errorMessage string
}

// WithIntError sets a custom error message for Int.
func WithIntError(msg string) func(*intOpts) {
	return func(o *intOpts) {
		o.errorMessage = msg
	}
}

// Float validates that a value is or can be converted to a float64.
func Float(opts ...func(*floatOpts)) Validator {
	o := &floatOpts{
		errorMessage: "value must be a number",
	}
	for _, opt := range opts {
		opt(o)
	}

	return ValidatorFunc(func(value any) ValidationResult {
		switch v := value.(type) {
		case float64:
			return Success(v)
		case float32:
			return Success(float64(v))
		case int:
			return Success(float64(v))
		case int32:
			return Success(float64(v))
		case int64:
			return Success(float64(v))
		case string:
			f, err := strconv.ParseFloat(v, 64)
			if err != nil {
				return Failure(o.errorMessage)
			}
			return Success(f)
		default:
			return Failure(o.errorMessage)
		}
	})
}

type floatOpts struct {
	errorMessage string
}

// WithFloatError sets a custom error message for Float.
func WithFloatError(msg string) func(*floatOpts) {
	return func(o *floatOpts) {
		o.errorMessage = msg
	}
}

// IntInRange validates that an integer is within a specified range.
func IntInRange(min, max int, opts ...func(*intRangeOpts)) Validator {
	o := &intRangeOpts{}
	for _, opt := range opts {
		opt(o)
	}

	return ValidatorFunc(func(value any) ValidationResult {
		// First validate it's an integer
		result := Int().Validate(value)
		if !result.IsValid {
			return result
		}

		intValue := result.Value.(int)

		if intValue < min {
			if o.errorMessage != "" {
				return Failure(o.errorMessage)
			}
			return Failuref("value must be at least %d", min)
		}

		if intValue > max {
			if o.errorMessage != "" {
				return Failure(o.errorMessage)
			}
			return Failuref("value must be at most %d", max)
		}

		return Success(intValue)
	})
}

type intRangeOpts struct {
	errorMessage string
}

// WithIntRangeError sets a custom error message for IntInRange.
func WithIntRangeError(msg string) func(*intRangeOpts) {
	return func(o *intRangeOpts) {
		o.errorMessage = msg
	}
}

// IntMin validates minimum integer value.
func IntMin(min int, opts ...func(*intRangeOpts)) Validator {
	o := &intRangeOpts{}
	for _, opt := range opts {
		opt(o)
	}

	return ValidatorFunc(func(value any) ValidationResult {
		result := Int().Validate(value)
		if !result.IsValid {
			return result
		}

		intValue := result.Value.(int)
		if intValue < min {
			if o.errorMessage != "" {
				return Failure(o.errorMessage)
			}
			return Failuref("value must be at least %d", min)
		}

		return Success(intValue)
	})
}

// IntMax validates maximum integer value.
func IntMax(max int, opts ...func(*intRangeOpts)) Validator {
	o := &intRangeOpts{}
	for _, opt := range opts {
		opt(o)
	}

	return ValidatorFunc(func(value any) ValidationResult {
		result := Int().Validate(value)
		if !result.IsValid {
			return result
		}

		intValue := result.Value.(int)
		if intValue > max {
			if o.errorMessage != "" {
				return Failure(o.errorMessage)
			}
			return Failuref("value must be at most %d", max)
		}

		return Success(intValue)
	})
}

// FloatInRange validates that a float is within a specified range.
func FloatInRange(min, max float64, opts ...func(*floatRangeOpts)) Validator {
	o := &floatRangeOpts{}
	for _, opt := range opts {
		opt(o)
	}

	return ValidatorFunc(func(value any) ValidationResult {
		result := Float().Validate(value)
		if !result.IsValid {
			return result
		}

		floatValue := result.Value.(float64)

		if floatValue < min {
			if o.errorMessage != "" {
				return Failure(o.errorMessage)
			}
			return Failuref("value must be at least %v", min)
		}

		if floatValue > max {
			if o.errorMessage != "" {
				return Failure(o.errorMessage)
			}
			return Failuref("value must be at most %v", max)
		}

		return Success(floatValue)
	})
}

type floatRangeOpts struct {
	errorMessage string
}

// WithFloatRangeError sets a custom error message for FloatInRange.
func WithFloatRangeError(msg string) func(*floatRangeOpts) {
	return func(o *floatRangeOpts) {
		o.errorMessage = msg
	}
}

// Positive validates that a number is positive (> 0).
func Positive(opts ...func(*positiveOpts)) Validator {
	o := &positiveOpts{
		allowZero: false,
	}
	for _, opt := range opts {
		opt(o)
	}

	return ValidatorFunc(func(value any) ValidationResult {
		result := Float().Validate(value)
		if !result.IsValid {
			return result
		}

		floatValue := result.Value.(float64)

		if o.allowZero {
			if floatValue < 0 {
				if o.errorMessage != "" {
					return Failure(o.errorMessage)
				}
				return Failure("value must be zero or positive")
			}
		} else {
			if floatValue <= 0 {
				if o.errorMessage != "" {
					return Failure(o.errorMessage)
				}
				return Failure("value must be positive")
			}
		}

		return Success(floatValue)
	})
}

type positiveOpts struct {
	allowZero    bool
	errorMessage string
}

// AllowZeroPositive allows zero in Positive validation.
func AllowZeroPositive() func(*positiveOpts) {
	return func(o *positiveOpts) {
		o.allowZero = true
	}
}

// WithPositiveError sets a custom error message for Positive.
func WithPositiveError(msg string) func(*positiveOpts) {
	return func(o *positiveOpts) {
		o.errorMessage = msg
	}
}

// Negative validates that a number is negative (< 0).
func Negative(opts ...func(*negativeOpts)) Validator {
	o := &negativeOpts{
		allowZero: false,
	}
	for _, opt := range opts {
		opt(o)
	}

	return ValidatorFunc(func(value any) ValidationResult {
		result := Float().Validate(value)
		if !result.IsValid {
			return result
		}

		floatValue := result.Value.(float64)

		if o.allowZero {
			if floatValue > 0 {
				if o.errorMessage != "" {
					return Failure(o.errorMessage)
				}
				return Failure("value must be zero or negative")
			}
		} else {
			if floatValue >= 0 {
				if o.errorMessage != "" {
					return Failure(o.errorMessage)
				}
				return Failure("value must be negative")
			}
		}

		return Success(floatValue)
	})
}

type negativeOpts struct {
	allowZero    bool
	errorMessage string
}

// AllowZeroNegative allows zero in Negative validation.
func AllowZeroNegative() func(*negativeOpts) {
	return func(o *negativeOpts) {
		o.allowZero = true
	}
}

// WithNegativeError sets a custom error message for Negative.
func WithNegativeError(msg string) func(*negativeOpts) {
	return func(o *negativeOpts) {
		o.errorMessage = msg
	}
}
