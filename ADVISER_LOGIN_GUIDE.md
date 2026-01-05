# How to Login as an Adviser

## Prerequisites

Before an adviser can login, the following steps must be completed:

### Step 1: Create an Adviser Record
1. Go to Django Admin: `http://127.0.0.1:8000/admin/`
2. Navigate to **Attendance > Advisers**
3. Click **"Add Adviser"**
4. Fill in the required fields:
   - **Name**: Full name of the adviser (e.g., "John Doe")
   - **Email**: Email address (must be unique)
   - **Employee ID**: (Optional, but recommended for username generation)
   - **Department**: (Optional)
5. Click **"Save"**

### Step 2: Create User Account for Adviser
1. In the Advisers list, select the adviser(s) you want to create accounts for
2. From the **"Action"** dropdown at the top, select **"Create login accounts for selected advisers"**
3. Click **"Go"**
4. This will:
   - Generate a username from Employee ID or email prefix
   - Create a Django User account
   - Set default password: **`adviser123`**
   - Link the User account to the Adviser profile

### Step 3: Assign Students to Adviser (Optional but Recommended)
1. Go to **Attendance > Students**
2. Edit a student record
3. Select the adviser from the **"Adviser"** dropdown
4. Save the student record

### Step 4: Set Password for Adviser (Optional)
1. In the Advisers list, select the adviser(s) you want to set passwords for
2. From the **"Action"** dropdown at the top, select **"Reset password to default for selected advisers"**
3. Click **"Go"**
4. This will reset the password to the default: **`adviser123`**
5. **Note**: To set a custom password, you can edit the User account directly in the **Users** admin section

### Step 5: Login as Adviser
1. Go to the login page: `http://127.0.0.1:8000/login/` or `http://127.0.0.1:8000/`
2. Enter credentials:
   - **Username / Employee ID**: 
     - **Employee ID** (recommended - can be used directly), OR
     - Username (generated from Employee ID or email prefix)
     - Example: If Employee ID is `EMP001`, you can login with `EMP001` or the generated username
   - **Password**: The password set in Step 4 (default: `adviser123`)
3. Click **"LOGIN"**

### After Login
- If the adviser has assigned students, they will be redirected to **Adviser Features** page
- If no students are assigned, they will be redirected to the **Dashboard**
- Advisers can:
  - View and approve/reject enrollment requests
  - View attendance logs for their assigned students
  - View student summaries and reports

## Important Notes

- **Login Methods**: 
  - You can login using your **Employee ID** directly (recommended)
  - You can also login using the generated **Username**
  - Both methods use the same password
- **Default Password**: The default password is `adviser123`. You can reset it using the admin action or set a custom password by editing the User account in the Users admin section.
- **Username Generation**: 
  - Username is generated from Employee ID first
  - If Employee ID is not provided, it uses the email prefix (part before @)
  - If username already exists, it adds the first name as suffix
- **Required Link**: The adviser must have a linked User account (created in Step 2) to login
- **Student Assignment**: While not strictly required for login, having assigned students enables full adviser functionality
- **Password Management**: 
  - Use the admin action "Reset password to default for selected advisers" to reset passwords
  - For custom passwords, edit the User account in the Users admin section at `http://127.0.0.1:8000/admin/auth/user/`

