# from django.db import models

# class UploadedDocument(models.Model):
#     file = models.FileField(upload_to="documents/")
#     uploaded_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return self.file.name


from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
import uuid


class User(AbstractUser):
    """
    Extended User model with additional fields
    """
    full_name = models.CharField(max_length=255)
    mobile_number = models.CharField(max_length=15, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Override username field to make it required
    username = models.CharField(max_length=150, unique=True)
    
    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
    
    def __str__(self):
        return f"{self.username} - {self.full_name}"


class ChatSession(models.Model):
    """
    Represents a conversation session for a user
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_sessions')
    title = models.CharField(max_length=255, default="New Chat")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_archived = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'chat_sessions'
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user', '-updated_at']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.title}"
    
    def get_message_count(self):
        return self.messages.count()
    
    def get_last_message(self):
        return self.messages.order_by('-created_at').first()


class ChatMessage(models.Model):
    """
    Individual messages in a chat session
    """
    ROLE_CHOICES = [
        ('user', 'User'),
        ('assistant', 'Assistant'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(ChatSession, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'chat_messages'
        ordering = ['created_at']
        indexes = [
            models.Index(fields=['session', 'created_at']),
        ]
    
    def __str__(self):
        return f"{self.session.title} - {self.role} - {self.created_at}"


class UploadedDocument(models.Model):
    """
    Documents uploaded by users
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='documents')
    session = models.ForeignKey(
        ChatSession, 
        on_delete=models.CASCADE, 
        related_name='documents',
        null=True,
        blank=True
    )
    file = models.FileField(upload_to='documents/%Y/%m/%d/')
    original_filename = models.CharField(max_length=255)
    file_size = models.BigIntegerField()  # in bytes
    file_type = models.CharField(max_length=50)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'uploaded_documents'
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['user', '-uploaded_at']),
            models.Index(fields=['session', '-uploaded_at']),
        ]
    
    def __str__(self):
        return f"{self.user.username} - {self.original_filename}"
    
    def get_file_size_mb(self):
        return round(self.file_size / (1024 * 1024), 2)


class DocumentEmbedding(models.Model):
    """
    Store embeddings for document chunks (for persistence)
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(UploadedDocument, on_delete=models.CASCADE, related_name='embeddings')
    chunk_text = models.TextField()
    chunk_index = models.IntegerField()
    embedding_vector = models.BinaryField()  # Store numpy array as binary
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'document_embeddings'
        ordering = ['chunk_index']
        indexes = [
            models.Index(fields=['document', 'chunk_index']),
        ]
    
    def __str__(self):
        return f"{self.document.original_filename} - Chunk {self.chunk_index}"