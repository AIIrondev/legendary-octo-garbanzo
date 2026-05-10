#!/usr/bin/env python3
"""
Invario PDF Audit Export - Implementation Verification Script

This script verifies that all components of the PDF audit export system
are correctly installed and configured.
"""

import sys
import os

def verify_files():
    """Verify all required files exist."""
    print("=" * 60)
    print("INVARIO PDF AUDIT EXPORT - INSTALLATION VERIFICATION")
    print("=" * 60)
    print()
    
    files_to_check = {
        "Core Module": [
            "Web/pdf_audit_export.py",
        ],
        "Flask Integration": [
            "Web/app.py",  # Should contain new routes
            "Web/templates/admin_audit.html",  # Should contain new buttons
        ],
        "Documentation": [
            "PDF_AUDIT_EXPORT_DOCUMENTATION.md",
            "PDF_IMPLEMENTATION_GUIDE.md",
            "QUICK_START_PDF_EXPORT.md",
        ]
    }
    
    base_path = os.path.dirname(os.path.abspath(__file__))
    all_ok = True
    
    for category, files in files_to_check.items():
        print(f"\n[{category}]")
        for filename in files:
            filepath = os.path.join(base_path, filename)
            exists = os.path.exists(filepath)
            status = "✓" if exists else "✗"
            print(f"  {status} {filename}")
            if not exists:
                all_ok = False
    
    return all_ok

def verify_dependencies():
    """Verify Python dependencies are installed."""
    print("\n[Python Dependencies]")
    
    dependencies = [
        ("reportlab", "PDF generation"),
        ("qrcode", "QR code generation"),
        ("pillow", "Image processing"),
        ("flask", "Web framework"),
        ("pymongo", "MongoDB driver"),
    ]
    
    all_ok = True
    for package, description in dependencies:
        try:
            __import__(package)
            print(f"  ✓ {package:15} - {description}")
        except ImportError:
            print(f"  ✗ {package:15} - {description}")
            all_ok = False
    
    return all_ok

def verify_routes():
    """Verify new routes are defined in app.py."""
    print("\n[Flask Routes]")
    
    routes_to_check = [
        "/admin/audit/export/pdf/quick",
        "/admin/audit/export/pdf/official",
    ]
    
    app_py_path = "Web/app.py"
    if not os.path.exists(app_py_path):
        print("  ✗ app.py not found")
        return False
    
    with open(app_py_path, 'r') as f:
        app_content = f.read()
    
    all_ok = True
    for route in routes_to_check:
        if route in app_content:
            print(f"  ✓ {route}")
        else:
            print(f"  ✗ {route}")
            all_ok = False
    
    return all_ok

def verify_template():
    """Verify template updates are in place."""
    print("\n[HTML Template Updates]")
    
    template_path = "Web/templates/admin_audit.html"
    if not os.path.exists(template_path):
        print("  ✗ admin_audit.html not found")
        return False
    
    with open(template_path, 'r') as f:
        template_content = f.read()
    
    checks = {
        "DIN 5008 Info Box": "DIN 5008",
        "PDF Quick-Check Button": "admin_audit_export_pdf_quick",
        "PDF Official Button": "admin_audit_export_pdf_official",
    }
    
    all_ok = True
    for check_name, check_string in checks.items():
        if check_string in template_content:
            print(f"  ✓ {check_name}")
        else:
            print(f"  ✗ {check_name}")
            all_ok = False
    
    return all_ok

def get_statistics():
    """Get implementation statistics."""
    print("\n[Implementation Statistics]")
    
    stats = {
        "Web/pdf_audit_export.py": "PDF Export Module",
        "PDF_AUDIT_EXPORT_DOCUMENTATION.md": "Technical Documentation",
        "PDF_IMPLEMENTATION_GUIDE.md": "Implementation Guide",
        "QUICK_START_PDF_EXPORT.md": "Quick Start Guide",
    }
    
    total_lines = 0
    for filename, description in stats.items():
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                lines = len(f.readlines())
            print(f"  {filename:45} {lines:5} lines - {description}")
            total_lines += lines
    
    print(f"\n  Total documentation: {total_lines} lines")

def print_next_steps():
    """Print next steps for the user."""
    print("\n" + "=" * 60)
    print("NEXT STEPS")
    print("=" * 60)
    print("""
1. CONFIGURE SCHOOL INFO (Optional)
   Edit config.json and add:
   {
     "school": {
       "name": "Your School Name",
       "address": "School Address",
       "postal_code": "12345",
       "city": "City Name",
       "school_number": "123456",
       "it_admin": "Admin Name"
     }
   }

2. RESTART THE SYSTEM
   ./start.sh
   or: python Web/app.py

3. TEST PDF EXPORTS
   - Login to http://localhost:8000/admin/audit
   - Click "🚀 Schnell-Check" for compact PDF
   - Click "📋 Amtlicher Bericht" for full DIN 5008 report

4. VERIFY COMPLIANCE
   - Check PDF opens in your PDF reader
   - Verify school info is correct
   - Test signature fields
   - Verify barrierefreiheit (accessibility)

5. DEPLOY TO PRODUCTION
   - Update your deployment scripts
   - Document new export procedures
   - Train staff on Quick-Check vs Official Report
""")

def main():
    """Run all verifications."""
    print()
    
    checks = [
        ("File Structure", verify_files),
        ("Dependencies", verify_dependencies),
        ("Flask Routes", verify_routes),
        ("HTML Template", verify_template),
    ]
    
    all_passed = True
    for name, check_func in checks:
        try:
            passed = check_func()
            if not passed:
                all_passed = False
        except Exception as e:
            print(f"\n✗ Error during {name} check: {e}")
            all_passed = False
    
    # Get statistics
    get_statistics()
    
    # Print results
    print("\n" + "=" * 60)
    if all_passed:
        print("✓ ALL VERIFICATION CHECKS PASSED!")
        print("=" * 60)
        print_next_steps()
    else:
        print("✗ SOME VERIFICATION CHECKS FAILED")
        print("=" * 60)
        print("\nPlease check the errors above and verify:")
        print("1. All files are in the correct locations")
        print("2. All dependencies are installed")
        print("3. app.py and admin_audit.html have been updated")
        sys.exit(1)
    
    print("\n" + "=" * 60)
    print("For detailed documentation, see:")
    print("  - QUICK_START_PDF_EXPORT.md (Start here!)")
    print("  - PDF_IMPLEMENTATION_GUIDE.md (Technical details)")
    print("  - PDF_AUDIT_EXPORT_DOCUMENTATION.md (Requirements)")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    main()
