import React, { useRef, useCallback, useEffect } from 'react';
import type { MFAInputProps } from '../types';
import { ELDER_LOGIN_THEME } from '../themes/elderTheme';

/**
 * MFA code input component with individual digit boxes.
 *
 * Features:
 * - Auto-advance on digit entry
 * - Backspace navigates to previous box
 * - Paste support for full code
 * - Auto-submit when all digits entered
 * - Elder-styled with gold accents
 */
export const MFAInput: React.FC<MFAInputProps> = ({
  length = 6,
  value,
  onChange,
  onComplete,
  disabled = false,
  error = false,
  colors,
}) => {
  const theme = { ...ELDER_LOGIN_THEME, ...colors };
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  // Split value into individual digits
  const digits = value.split('').slice(0, length);
  while (digits.length < length) {
    digits.push('');
  }

  // Focus first empty input on mount
  useEffect(() => {
    const firstEmpty = digits.findIndex((d) => !d);
    const targetIndex = firstEmpty === -1 ? length - 1 : firstEmpty;
    inputRefs.current[targetIndex]?.focus();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleChange = useCallback(
    (index: number, digitValue: string) => {
      // Only allow digits
      const digit = digitValue.replace(/\D/g, '').slice(-1);

      // Build new value
      const newDigits = [...digits];
      newDigits[index] = digit;
      const newValue = newDigits.join('');

      onChange(newValue);

      // Auto-advance to next input
      if (digit && index < length - 1) {
        inputRefs.current[index + 1]?.focus();
      }

      // Check for completion
      if (newValue.length === length && !newValue.includes('')) {
        onComplete?.(newValue);
      }
    },
    [digits, length, onChange, onComplete]
  );

  const handleKeyDown = useCallback(
    (index: number, e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Backspace') {
        if (!digits[index] && index > 0) {
          // Move to previous input if current is empty
          inputRefs.current[index - 1]?.focus();
          e.preventDefault();
        } else {
          // Clear current digit
          const newDigits = [...digits];
          newDigits[index] = '';
          onChange(newDigits.join(''));
        }
      } else if (e.key === 'ArrowLeft' && index > 0) {
        inputRefs.current[index - 1]?.focus();
        e.preventDefault();
      } else if (e.key === 'ArrowRight' && index < length - 1) {
        inputRefs.current[index + 1]?.focus();
        e.preventDefault();
      }
    },
    [digits, length, onChange]
  );

  const handlePaste = useCallback(
    (e: React.ClipboardEvent<HTMLInputElement>) => {
      e.preventDefault();
      const pasted = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, length);

      if (pasted) {
        console.debug('[LoginPage:MFA] Code pasted', { length: pasted.length });
        onChange(pasted);

        // Focus last filled input or the one after pasted content
        const targetIndex = Math.min(pasted.length, length - 1);
        inputRefs.current[targetIndex]?.focus();

        // Check for completion
        if (pasted.length === length) {
          onComplete?.(pasted);
        }
      }
    },
    [length, onChange, onComplete]
  );

  const handleFocus = useCallback((e: React.FocusEvent<HTMLInputElement>) => {
    e.target.select();
  }, []);

  return (
    <div className="flex justify-center gap-2 sm:gap-3">
      {digits.map((digit, index) => (
        <input
          key={index}
          ref={(el) => {
            inputRefs.current[index] = el;
          }}
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          maxLength={1}
          value={digit}
          onChange={(e) => handleChange(index, e.target.value)}
          onKeyDown={(e) => handleKeyDown(index, e)}
          onPaste={handlePaste}
          onFocus={handleFocus}
          disabled={disabled}
          aria-label={`Digit ${index + 1} of ${length}`}
          className={`
            w-10 h-12 sm:w-12 sm:h-14
            text-center text-xl font-mono font-semibold
            rounded-lg border-2
            transition-all duration-200
            ${theme.inputBackground}
            ${theme.inputText}
            ${error ? 'border-red-500 focus:border-red-500 focus:ring-red-500' : `${theme.inputBorder} ${theme.inputFocusBorder}`}
            focus:outline-none focus:ring-2 ${error ? 'focus:ring-red-500' : theme.inputFocusRing}
            ${disabled ? 'opacity-50 cursor-not-allowed' : ''}
          `}
        />
      ))}
    </div>
  );
};
