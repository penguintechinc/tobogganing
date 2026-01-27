package validation

import (
	"strings"
	"time"
)

// Date validates that a value is or can be parsed as a date.
func Date(opts ...func(*dateOpts)) Validator {
	o := &dateOpts{
		layout: "2006-01-02", // ISO 8601
	}
	for _, opt := range opts {
		opt(o)
	}

	return ValidatorFunc(func(value any) ValidationResult {
		switch v := value.(type) {
		case time.Time:
			return Success(v)
		case string:
			s := strings.TrimSpace(v)
			if s == "" {
				return Failure(o.getErrorMessage())
			}

			t, err := time.Parse(o.layout, s)
			if err != nil {
				return Failure(o.getErrorMessage())
			}
			return Success(t)
		default:
			return Failure("value must be a string or time.Time")
		}
	})
}

type dateOpts struct {
	layout       string
	errorMessage string
}

func (o *dateOpts) getErrorMessage() string {
	if o.errorMessage != "" {
		return o.errorMessage
	}
	return "invalid date format, expected: " + o.layout
}

// WithDateLayout sets the expected date layout.
func WithDateLayout(layout string) func(*dateOpts) {
	return func(o *dateOpts) {
		o.layout = layout
	}
}

// WithDateError sets a custom error message for Date.
func WithDateError(msg string) func(*dateOpts) {
	return func(o *dateOpts) {
		o.errorMessage = msg
	}
}

// DateTime validates that a value is or can be parsed as a datetime.
func DateTime(opts ...func(*dateTimeOpts)) Validator {
	o := &dateTimeOpts{
		layout: "2006-01-02T15:04:05", // ISO 8601
	}
	for _, opt := range opts {
		opt(o)
	}

	return ValidatorFunc(func(value any) ValidationResult {
		switch v := value.(type) {
		case time.Time:
			return Success(v)
		case string:
			s := strings.TrimSpace(v)
			if s == "" {
				return Failure(o.getErrorMessage())
			}

			t, err := time.Parse(o.layout, s)
			if err != nil {
				return Failure(o.getErrorMessage())
			}
			return Success(t)
		default:
			return Failure("value must be a string or time.Time")
		}
	})
}

type dateTimeOpts struct {
	layout       string
	errorMessage string
}

func (o *dateTimeOpts) getErrorMessage() string {
	if o.errorMessage != "" {
		return o.errorMessage
	}
	return "invalid datetime format, expected: " + o.layout
}

// WithDateTimeLayout sets the expected datetime layout.
func WithDateTimeLayout(layout string) func(*dateTimeOpts) {
	return func(o *dateTimeOpts) {
		o.layout = layout
	}
}

// WithDateTimeError sets a custom error message for DateTime.
func WithDateTimeError(msg string) func(*dateTimeOpts) {
	return func(o *dateTimeOpts) {
		o.errorMessage = msg
	}
}

// Time validates that a value is or can be parsed as a time.
func Time(opts ...func(*timeOpts)) Validator {
	o := &timeOpts{
		layout: "15:04:05",
	}
	for _, opt := range opts {
		opt(o)
	}

	return ValidatorFunc(func(value any) ValidationResult {
		switch v := value.(type) {
		case time.Time:
			return Success(v)
		case string:
			s := strings.TrimSpace(v)
			if s == "" {
				return Failure(o.getErrorMessage())
			}

			// Parse as time only (use reference date)
			t, err := time.Parse(o.layout, s)
			if err != nil {
				return Failure(o.getErrorMessage())
			}
			return Success(t)
		default:
			return Failure("value must be a string or time.Time")
		}
	})
}

type timeOpts struct {
	layout       string
	errorMessage string
}

func (o *timeOpts) getErrorMessage() string {
	if o.errorMessage != "" {
		return o.errorMessage
	}
	return "invalid time format, expected: " + o.layout
}

// WithTimeLayout sets the expected time layout.
func WithTimeLayout(layout string) func(*timeOpts) {
	return func(o *timeOpts) {
		o.layout = layout
	}
}

// WithTimeError sets a custom error message for Time.
func WithTimeError(msg string) func(*timeOpts) {
	return func(o *timeOpts) {
		o.errorMessage = msg
	}
}

// DateInRange validates that a date is within a specified range.
func DateInRange(minDate, maxDate time.Time, opts ...func(*dateRangeOpts)) Validator {
	o := &dateRangeOpts{
		layout:     "2006-01-02",
		hasMinDate: !minDate.IsZero(),
		hasMaxDate: !maxDate.IsZero(),
	}
	for _, opt := range opts {
		opt(o)
	}

	return ValidatorFunc(func(value any) ValidationResult {
		// First parse the date
		result := Date(WithDateLayout(o.layout)).Validate(value)
		if !result.IsValid {
			return result
		}

		dateValue := result.Value.(time.Time)

		// Check range
		if o.hasMinDate && dateValue.Before(minDate) {
			if o.errorMessage != "" {
				return Failure(o.errorMessage)
			}
			return Failuref("date must be on or after %s", minDate.Format(o.layout))
		}

		if o.hasMaxDate && dateValue.After(maxDate) {
			if o.errorMessage != "" {
				return Failure(o.errorMessage)
			}
			return Failuref("date must be on or before %s", maxDate.Format(o.layout))
		}

		return Success(dateValue)
	})
}

type dateRangeOpts struct {
	layout       string
	hasMinDate   bool
	hasMaxDate   bool
	errorMessage string
}

// WithDateRangeLayout sets the date layout for DateInRange.
func WithDateRangeLayout(layout string) func(*dateRangeOpts) {
	return func(o *dateRangeOpts) {
		o.layout = layout
	}
}

// WithDateRangeError sets a custom error message for DateInRange.
func WithDateRangeError(msg string) func(*dateRangeOpts) {
	return func(o *dateRangeOpts) {
		o.errorMessage = msg
	}
}

// DateAfter validates that a date is after a minimum date.
func DateAfter(minDate time.Time, opts ...func(*dateRangeOpts)) Validator {
	return DateInRange(minDate, time.Time{}, opts...)
}

// DateBefore validates that a date is before a maximum date.
func DateBefore(maxDate time.Time, opts ...func(*dateRangeOpts)) Validator {
	return DateInRange(time.Time{}, maxDate, opts...)
}

// RFC3339 validates datetime in RFC3339 format.
func RFC3339(opts ...func(*dateTimeOpts)) Validator {
	return DateTime(append(opts, WithDateTimeLayout(time.RFC3339))...)
}

// RFC3339Nano validates datetime in RFC3339Nano format.
func RFC3339Nano(opts ...func(*dateTimeOpts)) Validator {
	return DateTime(append(opts, WithDateTimeLayout(time.RFC3339Nano))...)
}
