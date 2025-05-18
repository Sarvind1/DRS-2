"""Utility functions for the document review system."""

import base64
import os
import pandas as pd
from datetime import datetime
from io import StringIO
import csv
import tempfile
from s3_utils import upload_file_to_s3, download_file_from_s3, get_s3_file_url, get_s3_client, get_full_s3_key, get_secret
import streamlit as st
from logger import logger
from streamlit_pdf_viewer import pdf_viewer

def load_data():
    """Load and prepare the review data."""
    try:
        if os.path.exists("data/Manual_Review.csv"):
            df_batches = pd.read_csv("data/Manual_Review.csv")
        else:
            data = {
                'Batch': ['B001', 'B001', 'B002', 'B002', 'B003'],
                'batch_count': [1, 2, 1, 2, 1],
                'portal_status': ['Pending', 'Accepted', 'Rejected', 'Pending', 'Accepted'],
                'reason': ['', 'Approved by agent', 'Missing information', '', 'Complete documentation']
            }
            df_batches = pd.DataFrame(data)

        # Get S3 client for checking files
        s3_client = get_s3_client()
        bucket_name = get_secret('bucket_name')
        if not bucket_name:
            st.error("S3 bucket name not configured")
            return pd.DataFrame()

        file_data = []
        for _, row in df_batches.iterrows():
            batch = row['Batch']
            count = row['batch_count']
            portal_status = row.get('portal_status', 'Unknown')
            reason = row.get('reason', '')

            for doc_type in ['CI', 'PL']:
                s3_key = f'{doc_type}/{batch}/{batch}_{count}.pdf'
                full_key = get_full_s3_key(s3_key)
                
                # Check if file exists in S3
                try:
                    s3_client.head_object(Bucket=bucket_name, Key=full_key)
                    file_exists = True
                except Exception as e:
                    st.error(f"File not found in S3: {full_key}")
                    continue

                file_data.append({
                    'batch': batch,
                    'type': doc_type,
                    'version': count,
                    'file_path': s3_key,
                    'filename': f'{batch}_{count}.pdf',
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'portal_status': portal_status,
                    'reason': reason
                })

        if not file_data:
            st.error("No files found in S3")
            return pd.DataFrame()

        return pd.DataFrame(file_data)
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        return pd.DataFrame()

def format_status_tag(status):
    """Format the review status tag HTML."""
    cls = 'status-reviewed' if status == 'reviewed' else 'status-not-reviewed'
    label = 'Reviewed' if status == 'reviewed' else 'Not Reviewed'
    return f"<span class='status-tag {cls}'>{label}</span>"

def format_portal_status(status, reason=""):
    """Format the portal status tag HTML."""
    tooltip = f" title='{reason}'" if reason else ""
    return f"<span class='portal-status'{tooltip}>{status}</span>"

def use_fallback_pdf(s3_key):
    """Use a local fallback PDF if available, or create HTML placeholder."""
    # Try local file if it exists
    local_path = f"static/documents/{s3_key}"
    if os.path.exists(local_path):
        st.info(f"Using local file: {local_path}")
        try:
            with open(local_path, "rb") as f:
                pdf_content = f.read()
                base64_pdf = base64.b64encode(pdf_content).decode('utf-8')
                pdf_display = f'''
                    <div style="width:100%; height:60vh;">
                        <embed
                            type="application/pdf"
                            src="data:application/pdf;base64,{base64_pdf}"
                            width="100%"
                            height="100%"
                            style="border: 1px solid #ddd; border-radius: 4px;"
                        />
                    </div>
                '''
                return pdf_display
        except Exception as local_error:
            st.warning(f"Error reading local file: {str(local_error)}")
    
    # Parse document info from s3_key
    try:
        parts = s3_key.split('/')
        doc_type = parts[0] if len(parts) > 0 else "Unknown"
        batch = parts[1] if len(parts) > 1 else "Unknown"
        filename = parts[2] if len(parts) > 2 else s3_key
        
        version = "Unknown"
        if '_' in filename:
            version = filename.split('_')[-1].split('.')[0]
    except:
        doc_type = "Unknown"
        batch = "Unknown"
        version = "Unknown"
    
    # Display HTML placeholder instead
    return f'''
        <div style="width:100%; height:60vh; border:1px solid #ddd; background:#f8f9fa; overflow:auto; padding:20px;">
            <div style="margin:20px; border:2px solid #333; padding:40px; background:white; min-height:500px; position:relative;">
                <h2 style="text-align:center; margin-bottom:40px; color:#333;">{doc_type} Document</h2>
                <div style="margin-bottom:30px;">
                    <strong>Batch:</strong> {batch}<br>
                    <strong>Version:</strong> {version}<br>
                    <strong>File Path:</strong> {s3_key}
                </div>
                <div style="margin-bottom:30px;">
                    <h3>Document Content (Preview Unavailable)</h3>
                    <p style="color:#666;">This is a placeholder for document content. The actual document could not be loaded from S3.</p>
                    <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit. Nullam auctor, nisl eget ultricies tincidunt...</p>
                </div>
                <div style="position:absolute; bottom:20px; right:20px; color:#999; font-size:12px;">
                    Demo Mode - PDF Preview Unavailable
                </div>
            </div>
        </div>
    '''

def embed_pdf_base64(s3_key):
    """Embed a PDF file from S3 using enhanced viewer."""
    try:
        # Get S3 client and bucket name
        s3_client = get_s3_client()
        bucket_name = get_secret('bucket_name')
        
        if not bucket_name:
            st.write("⚠️ S3 bucket name not configured")
            return ""
            
        full_key = get_full_s3_key(s3_key)
        st.write(f"📄 Loading PDF: {s3_key}")
        
        try:
            # Generate a pre-signed URL for the PDF
            url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': full_key},
                ExpiresIn=3600  # URL expires in 1 hour
            )
            
            st.write("✅ PDF URL generated successfully")
            
            # Create PDF viewer HTML with enhanced controls
            return f'''
                <div style="width:100%; height:80vh; position:relative;">
                    <iframe
                        src="{url}#toolbar=1&navpanes=1&scrollbar=1&view=FitH"
                        width="100%"
                        height="100%"
                        style="border: 1px solid #ddd; border-radius: 4px; position:absolute; top:0; left:0; right:0; bottom:0;"
                        allowfullscreen
                    ></iframe>
                </div>
                <style>
                    /* Ensure iframe takes full width and maintains aspect ratio */
                    iframe {{
                        aspect-ratio: 16/9;
                        min-height: 80vh;
                        background: white;
                    }}
                    
                    /* Add responsive behavior */
                    @media (max-width: 768px) {{
                        iframe {{
                            min-height: 60vh;
                        }}
                    }}
                    
                    /* Improve iframe container */
                    div:has(> iframe) {{
                        margin: 0;
                        padding: 0;
                        overflow: hidden;
                        background: #f8f9fa;
                        border-radius: 4px;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    }}
                </style>
            '''
        except Exception as s3_error:
            error_msg = f"❌ Error accessing PDF: {str(s3_error)}"
            st.write(error_msg)
            return ""
    except Exception as e:
        error_msg = f"❌ Error setting up PDF viewer: {str(e)}"
        st.write(error_msg)
        return ""

def generate_comparison_pairs(versions):
    """Generate pairs of versions for comparison."""
    if len(versions) < 2:
        return []
    pairs = [(versions[i], versions[i+1]) for i in range(len(versions)-1)]
    if len(versions) > 2:
        pairs.append((versions[0], versions[-1]))
    return pairs

def export_audit_trail(audit_trail):
    """Export audit trail to CSV format and save to S3."""
    if not audit_trail:
        return ""

    all_keys = set().union(*(row.keys() for row in audit_trail))
    fieldnames = list(all_keys)

    # Create CSV in memory
    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in audit_trail:
        writer.writerow({key: row.get(key) for key in fieldnames})
    
    # Save to temporary file and upload to S3
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
        temp_file.write(buffer.getvalue())
        temp_file.flush()
        
        # Generate S3 key with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d")
        s3_key = f'audit/audit_trails/{timestamp}/audit_trail.csv'
        
        # Upload to S3
        upload_file_to_s3(temp_file.name, s3_key)
        
        # Clean up temporary file
        os.unlink(temp_file.name)
    
    return buffer.getvalue() 