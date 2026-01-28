# FormBuilder Example Usage

This document shows how to refactor existing forms to use the FormBuilder component.

## Example: Users.tsx Refactored

### Before (Original Implementation - Lines 138-202)

```tsx
{showCreateModal && (
  <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
    <div className="card w-full max-w-md">
      <h2 className="text-xl font-bold text-gold-400 mb-4">Create New User</h2>
      <form onSubmit={handleCreateUser} className="space-y-4">
        <div>
          <label className="block text-sm text-dark-400 mb-1">Full Name</label>
          <input
            type="text"
            value={newUser.full_name}
            onChange={(e) => setNewUser({ ...newUser, full_name: e.target.value })}
            className="input"
            required
          />
        </div>
        {/* More fields... */}
      </form>
    </div>
  </div>
)}
```

### After (Using FormBuilder - Modal Mode)

```tsx
import { FormBuilder, FieldConfig } from '@penguin/react-libs';

// Define fields configuration (outside component for performance)
const userFields: FieldConfig[] = [
  {
    name: 'full_name',
    label: 'Full Name',
    type: 'text',
    required: true,
    placeholder: 'John Doe',
  },
  {
    name: 'email',
    label: 'Email',
    type: 'email',
    required: true,
    placeholder: 'user@example.com',
  },
  {
    name: 'password',
    label: 'Password',
    type: 'password',
    required: true,
    minLength: 8,
    helperText: 'Minimum 8 characters',
  },
  {
    name: 'role',
    label: 'Role',
    type: 'select',
    required: true,
    defaultValue: 'viewer',
    options: [
      { value: 'viewer', label: 'Viewer' },
      { value: 'maintainer', label: 'Maintainer' },
      { value: 'admin', label: 'Admin' },
    ],
  },
];

export default function Users() {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCreateUser = async (data: Record<string, any>) => {
    try {
      await usersApi.create(data);
      setShowCreateModal(false);
      fetchUsers();
      setError(null);
    } catch (err) {
      setError('Failed to create user');
      throw err; // Re-throw to keep form in submitting state
    }
  };

  return (
    <div>
      {/* Header and table... */}

      {/* Create User Modal - Much simpler! */}
      <FormBuilder
        mode="modal"
        isOpen={showCreateModal}
        fields={userFields}
        title="Create New User"
        submitLabel="Create User"
        cancelLabel="Cancel"
        onSubmit={handleCreateUser}
        onCancel={() => setShowCreateModal(false)}
        error={error}
      />
    </div>
  );
}
```

**Benefits:**
- ✅ Removed 60+ lines of form code
- ✅ Built-in validation
- ✅ Consistent styling
- ✅ Error handling
- ✅ Loading states
- ✅ Accessible modal

## Inline Mode Example

### Editing User Profile

```tsx
import { FormBuilder, FieldConfig } from '@penguin/react-libs';
import Card from '../components/Card';

const profileFields: FieldConfig[] = [
  {
    name: 'full_name',
    label: 'Full Name',
    type: 'text',
    required: true,
  },
  {
    name: 'email',
    label: 'Email',
    type: 'email',
    required: true,
  },
  {
    name: 'bio',
    label: 'Bio',
    type: 'textarea',
    rows: 4,
    placeholder: 'Tell us about yourself...',
  },
];

export default function ProfileEdit() {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);

  const handleSubmit = async (data: Record<string, any>) => {
    await usersApi.update(user.id, data);
    // Optionally redirect or show success message
  };

  return (
    <Card title="Edit Profile">
      <FormBuilder
        mode="inline"
        fields={profileFields}
        initialData={user}
        submitLabel="Save Changes"
        onSubmit={handleSubmit}
        validateOnBlur={true}
      />
    </Card>
  );
}
```

## Advanced Examples

### Custom Validation

```tsx
const fields: FieldConfig[] = [
  {
    name: 'username',
    label: 'Username',
    type: 'text',
    required: true,
    validate: (value) => {
      if (value && !/^[a-zA-Z0-9_]+$/.test(value)) {
        return 'Username can only contain letters, numbers, and underscores';
      }
      return null;
    },
  },
  {
    name: 'confirm_password',
    label: 'Confirm Password',
    type: 'password',
    required: true,
    validate: (value) => {
      const password = document.querySelector('[name="password"]')?.value;
      if (value !== password) {
        return 'Passwords do not match';
      }
      return null;
    },
  },
];
```

### Conditional Fields (onChange Handler)

```tsx
const [showAdvanced, setShowAdvanced] = useState(false);

const fields: FieldConfig[] = [
  {
    name: 'account_type',
    label: 'Account Type',
    type: 'select',
    options: [
      { value: 'basic', label: 'Basic' },
      { value: 'advanced', label: 'Advanced' },
    ],
    onChange: (value) => {
      setShowAdvanced(value === 'advanced');
    },
  },
  ...(showAdvanced ? [
    {
      name: 'advanced_setting',
      label: 'Advanced Setting',
      type: 'text',
    }
  ] : []),
];
```

### Radio Buttons

```tsx
const fields: FieldConfig[] = [
  {
    name: 'subscription',
    label: 'Subscription Plan',
    type: 'radio',
    required: true,
    options: [
      { value: 'free', label: 'Free - $0/month' },
      { value: 'pro', label: 'Pro - $10/month' },
      { value: 'enterprise', label: 'Enterprise - $50/month' },
    ],
  },
];
```

### Checkbox

```tsx
const fields: FieldConfig[] = [
  {
    name: 'newsletter',
    label: 'Subscribe to newsletter',
    type: 'checkbox',
    defaultValue: true,
  },
  {
    name: 'terms',
    label: 'I agree to the terms and conditions',
    type: 'checkbox',
    required: true,
    validate: (value) => {
      if (!value) {
        return 'You must accept the terms and conditions';
      }
      return null;
    },
  },
];
```

### Date/Time Fields

```tsx
const fields: FieldConfig[] = [
  {
    name: 'birth_date',
    label: 'Date of Birth',
    type: 'date',
    required: true,
    max: new Date().toISOString().split('T')[0], // Today
  },
  {
    name: 'appointment',
    label: 'Appointment Time',
    type: 'datetime-local',
    required: true,
    min: new Date().toISOString().slice(0, 16), // Now
  },
];
```

## Migration Checklist

When migrating existing forms to FormBuilder:

1. ✅ Define field configuration array
2. ✅ Remove manual state management (`useState` for form fields)
3. ✅ Remove manual input handlers (`onChange`, `onBlur`)
4. ✅ Replace modal markup with `mode="modal"`
5. ✅ Simplify submit handler (receives data object)
6. ✅ Remove manual validation code
7. ✅ Update error handling (pass `error` prop)
8. ✅ Remove loading state management (handled by FormBuilder)
9. ✅ Test form validation
10. ✅ Test form submission
