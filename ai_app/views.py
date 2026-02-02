from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count
import json
from groq import Groq
from django.conf import settings
from pypdf import PdfReader
import docx
import os
from datetime import datetime

from .models import User, ChatSession, ChatMessage, UploadedDocument
from .rag_utils import retrieve_chunks, process_document_text_with_storage, clear_session_documents

client = Groq(api_key=settings.GROQ_API_KEY)


# ═══════════════════════════════════════════════════════════════════
# AUTHENTICATION VIEWS
# ═══════════════════════════════════════════════════════════════════

def register_page(request):
    """Render registration page"""
    if request.user.is_authenticated:
        return redirect('chat_page')
    return render(request, 'ai_app/register.html')


def login_page(request):
    """Render login page"""
    if request.user.is_authenticated:
        return redirect('chat_page')
    return render(request, 'ai_app/login.html')


@csrf_exempt
def register_user(request):
    """Handle user registration"""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            
            # Validate required fields
            required_fields = ['full_name', 'mobile_number', 'username', 'password']
            for field in required_fields:
                if not data.get(field):
                    return JsonResponse(
                        {"error": f"{field.replace('_', ' ').title()} is required"}, 
                        status=400
                    )
            
            full_name = data['full_name'].strip()
            mobile_number = data['mobile_number'].strip()
            username = data['username'].strip().lower()
            password = data['password']
            
            # Validate mobile number
            if not mobile_number.isdigit() or len(mobile_number) < 10:
                return JsonResponse(
                    {"error": "Invalid mobile number. Must be at least 10 digits."}, 
                    status=400
                )
            
            # Check if username already exists
            if User.objects.filter(username=username).exists():
                return JsonResponse(
                    {"error": "Username already exists. Please choose another."}, 
                    status=400
                )
            
            # Check if mobile number already exists
            if User.objects.filter(mobile_number=mobile_number).exists():
                return JsonResponse(
                    {"error": "Mobile number already registered."}, 
                    status=400
                )
            
            # Create user
            user = User.objects.create_user(
                username=username,
                password=password,
                full_name=full_name,
                mobile_number=mobile_number,
                email=data.get('email', '')
            )
            
            # Auto login after registration
            login(request, user)
            
            return JsonResponse({
                "message": "Registration successful!",
                "user": {
                    "username": user.username,
                    "full_name": user.full_name
                }
            })
            
        except Exception as e:
            return JsonResponse(
                {"error": f"Registration failed: {str(e)}"}, 
                status=500
            )
    
    return JsonResponse({"error": "POST request required"}, status=405)


@csrf_exempt
def login_user(request):
    """Handle user login"""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            
            username = data.get('username', '').strip().lower()
            password = data.get('password', '')
            
            if not username or not password:
                return JsonResponse(
                    {"error": "Username and password are required"}, 
                    status=400
                )
            
            # Authenticate user
            user = authenticate(request, username=username, password=password)
            
            if user is not None:
                login(request, user)
                return JsonResponse({
                    "message": "Login successful!",
                    "user": {
                        "username": user.username,
                        "full_name": user.full_name
                    }
                })
            else:
                return JsonResponse(
                    {"error": "Invalid username or password"}, 
                    status=401
                )
            
        except Exception as e:
            return JsonResponse(
                {"error": f"Login failed: {str(e)}"}, 
                status=500
            )
    
    return JsonResponse({"error": "POST request required"}, status=405)


@csrf_exempt
@login_required
def logout_user(request):
    """Handle user logout"""
    logout(request)
    return JsonResponse({"message": "Logged out successfully"})


# ═══════════════════════════════════════════════════════════════════
# CHAT VIEWS
# ═══════════════════════════════════════════════════════════════════

@login_required
def chat_page(request):
    """Render the chat interface"""
    return render(request, "ai_app/chat.html")


@csrf_exempt
@login_required
def create_chat_session(request):
    """Create a new chat session"""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            title = data.get('title', f"Chat - {datetime.now().strftime('%b %d, %Y %I:%M %p')}")
            
            session = ChatSession.objects.create(
                user=request.user,
                title=title
            )
            
            return JsonResponse({
                "session_id": str(session.id),
                "title": session.title,
                "created_at": session.created_at.isoformat()
            })
            
        except Exception as e:
            return JsonResponse(
                {"error": f"Failed to create session: {str(e)}"}, 
                status=500
            )
    
    return JsonResponse({"error": "POST request required"}, status=405)


@csrf_exempt
@login_required
def get_chat_sessions(request):
    """Get all chat sessions for the current user"""
    if request.method == "GET":
        try:
            sessions = ChatSession.objects.filter(
                user=request.user,
                is_archived=False
            ).annotate(
                message_count=Count('messages')
            )
            
            sessions_data = [{
                "id": str(session.id),
                "title": session.title,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "message_count": session.message_count,
                "last_message": session.get_last_message().content[:50] + "..." 
                    if session.get_last_message() else None
            } for session in sessions]
            
            return JsonResponse({
                "sessions": sessions_data,
                "total": len(sessions_data)
            })
            
        except Exception as e:
            return JsonResponse(
                {"error": f"Failed to fetch sessions: {str(e)}"}, 
                status=500
            )
    
    return JsonResponse({"error": "GET request required"}, status=405)


@csrf_exempt
@login_required
def get_chat_history(request, session_id):
    """Get all messages for a specific chat session"""
    if request.method == "GET":
        try:
            session = ChatSession.objects.get(id=session_id, user=request.user)
            messages = session.messages.all()
            
            messages_data = [{
                "id": str(msg.id),
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at.isoformat()
            } for msg in messages]
            
            # Get documents for this session
            documents = session.documents.all()
            documents_data = [{
                "id": str(doc.id),
                "filename": doc.original_filename,
                "size": doc.get_file_size_mb(),
                "uploaded_at": doc.uploaded_at.isoformat()
            } for doc in documents]
            
            return JsonResponse({
                "session_id": str(session.id),
                "title": session.title,
                "messages": messages_data,
                "documents": documents_data
            })
            
        except ChatSession.DoesNotExist:
            return JsonResponse(
                {"error": "Chat session not found"}, 
                status=404
            )
        except Exception as e:
            return JsonResponse(
                {"error": f"Failed to fetch chat history: {str(e)}"}, 
                status=500
            )
    
    return JsonResponse({"error": "GET request required"}, status=405)


@csrf_exempt
@login_required
def update_chat_title(request, session_id):
    """Update chat session title"""
    if request.method == "PUT":
        try:
            data = json.loads(request.body)
            new_title = data.get('title', '').strip()
            
            if not new_title:
                return JsonResponse(
                    {"error": "Title cannot be empty"}, 
                    status=400
                )
            
            session = ChatSession.objects.get(id=session_id, user=request.user)
            session.title = new_title
            session.save()
            
            return JsonResponse({
                "message": "Title updated successfully",
                "title": session.title
            })
            
        except ChatSession.DoesNotExist:
            return JsonResponse(
                {"error": "Chat session not found"}, 
                status=404
            )
        except Exception as e:
            return JsonResponse(
                {"error": f"Failed to update title: {str(e)}"}, 
                status=500
            )
    
    return JsonResponse({"error": "PUT request required"}, status=405)


@csrf_exempt
@login_required
def delete_chat_session(request, session_id):
    """Delete a chat session"""
    if request.method == "DELETE":
        try:
            session = ChatSession.objects.get(id=session_id, user=request.user)
            
            # Clear associated documents from RAG store
            clear_session_documents(session_id)
            
            session.delete()
            
            return JsonResponse({
                "message": "Chat session deleted successfully"
            })
            
        except ChatSession.DoesNotExist:
            return JsonResponse(
                {"error": "Chat session not found"}, 
                status=404
            )
        except Exception as e:
            return JsonResponse(
                {"error": f"Failed to delete session: {str(e)}"}, 
                status=500
            )
    
    return JsonResponse({"error": "DELETE request required"}, status=405)


# ═══════════════════════════════════════════════════════════════════
# AI CHAT FUNCTIONALITY
# ═══════════════════════════════════════════════════════════════════

def ask_ai_with_docs(question, session_id):
    """
    Enhanced AI question answering with session-specific context
    """
    # Retrieve relevant context chunks for this session
    context_chunks = retrieve_chunks(question, session_id=session_id, top_k=5)
    
    if context_chunks and context_chunks[0] == "No document uploaded yet.":
        return "Please upload a document first before asking questions."
    
    context = "\n\n---\n\n".join([
        f"[Excerpt {i+1}]:\n{chunk}" 
        for i, chunk in enumerate(context_chunks)
    ])
    
    prompt = f"""You are a helpful AI assistant analyzing documents. Your task is to answer questions based ONLY on the provided document context.

INSTRUCTIONS:
1. Read the context carefully
2. Answer the question accurately using ONLY information from the context
3. If the context doesn't contain enough information, say "I cannot find this information in the provided document"
4. Be specific and cite relevant parts when possible
5. Keep your answer clear, concise, and well-structured

DOCUMENT CONTEXT:
{context}

USER QUESTION:
{question}

ANSWER:"""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system", 
                    "content": "You are a precise document analysis assistant. Answer questions based only on the provided context."
                },
                {
                    "role": "user", 
                    "content": prompt
                }
            ],
            temperature=0.3,
            max_tokens=1024,
            top_p=0.9
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        return f"Error generating response: {str(e)}"

@csrf_exempt
@login_required
def ai_chat(request):
    """Handle chat requests with automatic session management"""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            question = data.get("question", "").strip()
            session_id = data.get("session_id")

            if not question:
                return JsonResponse({"error": "Question is required"}, status=400)

            # 🔹 If no session_id → create new session automatically
            if not session_id:
                session = ChatSession.objects.create(
                    user=request.user,
                    title=f"Chat - {datetime.now().strftime('%b %d, %Y %I:%M %p')}"
                )
                session_id = str(session.id)
            else:
                try:
                    session = ChatSession.objects.get(id=session_id, user=request.user)
                except ChatSession.DoesNotExist:
                    return JsonResponse({"error": "Invalid session"}, status=404)

            # Save user message
            ChatMessage.objects.create(
                session=session,
                role="user",
                content=question
            )

            # Get AI response
            answer = ask_ai_with_docs(question, session_id)

            # Save AI response
            ai_message = ChatMessage.objects.create(
                session=session,
                role="assistant",
                content=answer
            )

            session.save()  # update timestamp

            return JsonResponse({
                "answer": answer,
                "session_id": session_id,  # 🔹 send back to frontend
                "message_id": str(ai_message.id),
                "created_at": ai_message.created_at.isoformat()
            })

        except Exception as e:
            return JsonResponse({"error": f"Server error: {str(e)}"}, status=500)

    return JsonResponse({"error": "POST request required"}, status=405)


# ═══════════════════════════════════════════════════════════════════
# DOCUMENT UPLOAD
# ═══════════════════════════════════════════════════════════════════

def extract_text_from_pdf(file_path):
    """Extract text from PDF"""
    reader = PdfReader(file_path)
    text = ""
    for page_num, page in enumerate(reader.pages, 1):
        page_text = page.extract_text() or ""
        if page_text.strip():
            text += f"\n--- Page {page_num} ---\n{page_text}"
    return text


def extract_text_from_docx(file_path):
    """Extract text from Word documents"""
    doc = docx.Document(file_path)
    return "\n".join([para.text for para in doc.paragraphs if para.text.strip()])


def extract_text_from_txt(file_path):
    """Extract text from TXT files"""
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()


@csrf_exempt
@login_required
def upload_document(request):
    """Handle document upload with user and session association"""
    if request.method == "POST":
        try:
            file = request.FILES.get("file")
            session_id = request.POST.get("session_id")
            
            if not file:
                return JsonResponse({"error": "No file uploaded"}, status=400)
            
            if not session_id:
                return JsonResponse({"error": "Session ID is required"}, status=400)
            
            # Verify session
            try:
                session = ChatSession.objects.get(id=session_id, user=request.user)
            except ChatSession.DoesNotExist:
                return JsonResponse({"error": "Invalid session"}, status=404)
            
            # Validate file
            if file.size > 10 * 1024 * 1024:
                return JsonResponse(
                    {"error": "File size too large. Maximum 10MB."}, 
                    status=400
                )
            
            file_ext = os.path.splitext(file.name.lower())[1]
            if file_ext not in ['.pdf', '.docx', '.doc', '.txt']:
                return JsonResponse(
                    {"error": "Unsupported file type"}, 
                    status=400
                )
            
            # Save document
            doc = UploadedDocument.objects.create(
                user=request.user,
                session=session,
                file=file,
                original_filename=file.name,
                file_size=file.size,
                file_type=file_ext
            )
            
            # Extract text
            file_path = doc.file.path
            if file_ext == '.pdf':
                text = extract_text_from_pdf(file_path)
            elif file_ext in ['.docx', '.doc']:
                text = extract_text_from_docx(file_path)
            else:
                text = extract_text_from_txt(file_path)
            
            if not text or len(text.strip()) < 10:
                doc.delete()
                return JsonResponse(
                    {"error": "Could not extract text from document"}, 
                    status=400
                )
            
            # Process document with session ID
            process_document_text_with_storage(
                text, 
                doc_id=str(doc.id),
                session_id=session_id,
                doc_name=file.name
            )
            
            doc.processed = True
            doc.save()
            
            return JsonResponse({
                "message": "Document uploaded successfully",
                "document_id": str(doc.id),
                "filename": file.name,
                "size": doc.get_file_size_mb()
            })
            
        except Exception as e:
            return JsonResponse(
                {"error": f"Upload failed: {str(e)}"}, 
                status=500
            )
    
    return JsonResponse({"error": "POST request required"}, status=405)