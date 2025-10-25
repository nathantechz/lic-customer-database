# Customer Update Feature - User Guide

## Overview
The LIC Customer Database Streamlit app now includes comprehensive customer editing functionality, allowing you to update customer details directly through the web interface.

## Features Added

### ✏️ Edit Customer Details
- **Phone Number**: Primary contact number
- **Alternative Phone**: Secondary contact number  
- **Email**: Customer email address
- **Aadhaar Number**: Aadhaar identification number
- **Date of Birth**: Customer's DOB
- **Occupation**: Customer's profession
- **Full Address**: Complete address information
- **Notes**: Additional notes or comments

### 🔍 Enhanced Customer Display
Each customer card now shows:
- All available customer information in organized columns
- **Edit button** for quick access to editing
- Better formatted display with icons for easy identification
- Separate sections for basic info, personal info, and notes

### 💾 Database Updates
- **Automatic timestamps**: `last_updated` field is automatically set
- **Validation**: Empty fields are stored as NULL in database
- **Error handling**: Comprehensive error messages for any issues
- **Success feedback**: Clear confirmation when updates are saved

## How to Use

### 1. Search for a Customer
- Use the search box to find customers by name, policy number, phone, or agent code
- Or click "Show All" to see all customers

### 2. Edit Customer Details
- Click the **"✏️ Edit"** button next to any customer
- Fill in the form with updated information
- Fields can be left empty if no information is available
- Click **"💾 Update Details"** to save changes
- Click **"❌ Cancel"** to return without saving

### 3. View Updated Information
- After saving, you'll return to the customer list
- The customer's "Last Updated" timestamp will show the recent change
- All updated information will be visible in the customer card

## Database Schema

The following fields are editable in the customers table:
```sql
phone_number TEXT
alt_phone_number TEXT  
email TEXT
aadhaar_number TEXT
date_of_birth TEXT
occupation TEXT
full_address TEXT
notes TEXT
last_updated TIMESTAMP (automatically updated)
```

## Technical Implementation

### Update Function
```python
def update_customer_details(customer_id, updates):
    # Validates and updates customer information
    # Returns success status and message
```

### Edit Form
```python
def show_customer_edit_form(customer_data):
    # Displays form with current customer data
    # Handles form submission and validation
```

### Customer Retrieval
```python
def get_customer_by_id(customer_id):
    # Fetches complete customer data including policies
    # Returns dictionary with all customer information
```

## Session State Management

The app uses Streamlit session state to manage:
- **`edit_customer_id`**: Tracks which customer is being edited
- **`show_results`**: Controls search results display
- Seamless transitions between view and edit modes

## Error Handling

The system includes comprehensive error handling for:
- **Database connection issues**: Clear error messages
- **Customer not found**: Graceful handling of missing records  
- **Update failures**: Detailed error information
- **Form validation**: Prevents invalid data entry

## UI Improvements

### Deprecated Warnings Fixed
- Updated all `use_container_width=True` to `width="stretch"`
- Eliminated Streamlit deprecation warnings
- Modern, clean interface design

### Enhanced Layout
- **3-column customer info display**: Better organization
- **Responsive buttons**: Proper width management
- **Clear visual hierarchy**: Icons and formatting for easy scanning
- **Form organization**: Logical grouping of related fields

## Testing

A test script is included: `scripts/test_customer_update.py`
- Verifies database update functionality
- Shows sample customer data
- Confirms successful updates and rollbacks
- Provides debugging information

## Usage Examples

### Update Phone Number
1. Search for "Nagarajan"
2. Click "✏️ Edit" button
3. Enter phone number: `9876543210`
4. Click "💾 Update Details"
5. Success message confirms update

### Add Complete Customer Information
1. Find customer with minimal data
2. Click "✏️ Edit"
3. Fill in all available fields:
   - Phone: `9876543210`
   - Email: `customer@example.com`
   - DOB: `1990-01-15`
   - Occupation: `Engineer`
   - Address: `123 Main St, City, State`
   - Notes: `Preferred contact after 6 PM`
4. Save changes

### View Update History
- Check the "Last Updated" field in customer cards
- Recent updates show current timestamp
- Compare with "Created" date to see modification history

## Best Practices

### Data Entry
- **Consistent formatting**: Use standard formats for dates (YYYY-MM-DD)
- **Complete information**: Fill in as many fields as possible
- **Verify accuracy**: Double-check important details like phone and email
- **Use notes field**: Add context or special instructions

### Database Maintenance
- **Regular backups**: The update feature modifies live data
- **Verify changes**: Check customer cards after updates
- **Monitor timestamps**: Use last_updated field to track recent changes

## Troubleshooting

### Common Issues

**Edit button not working**
- Refresh the page (F5)
- Check browser console for JavaScript errors
- Ensure Streamlit app is running

**Form not saving**
- Check database connection in sidebar
- Verify all required fields are valid
- Look for error messages in the app

**Customer not found**
- Customer may have been deleted
- Check search criteria
- Refresh the customer list

**Database locked errors**
- Another process may be using the database
- Close other database connections
- Restart the Streamlit app

## Future Enhancements

Potential improvements for the edit functionality:
- **Bulk updates**: Edit multiple customers at once
- **Field validation**: Format checking for phone, email, etc.
- **History tracking**: Maintain audit trail of changes
- **Photo upload**: Add customer photos through the interface
- **Advanced search**: Filter by editable fields
- **Export updated data**: CSV export with recent changes

## Support

For issues or questions about the customer update feature:
1. Check the Streamlit app error messages
2. Run the test script: `python scripts/test_customer_update.py`
3. Check database connection in the sidebar
4. Verify customer data exists in the database

The edit functionality is fully integrated with the existing PDF processing and search features, providing a complete customer management solution.