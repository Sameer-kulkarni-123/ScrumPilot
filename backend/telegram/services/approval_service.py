"""
Approval Service

Creates approval requests and sends Telegram notifications.
This is called by pipelines when they need human approval.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from backend.db.connection import get_session
from backend.db.models import User, ApprovalRequest
from backend.db import crud

logger = logging.getLogger(__name__)


class ApprovalService:
    """Service for creating and managing approval requests."""
    
    @staticmethod
    def create_epic_approval(
        epics_data: Dict[str, Any],
        requested_by_user_id: int,
        assigned_to_user_id: int,
        priority: str = 'high'
    ) -> int:
        """
        Create approval request for epic creation.
        
        Args:
            epics_data: Dict with 'epics' list
            requested_by_user_id: User who requested (usually system/bot)
            assigned_to_user_id: PM who should approve
            priority: 'low', 'normal', 'high', 'urgent'
        
        Returns:
            approval_id
        """
        with get_session() as session:
            # Create approval request
            approval = ApprovalRequest(
                request_type='epic_creation',
                entity_type='epic',
                entity_id=0,  # No specific entity yet
                requested_by=requested_by_user_id,
                assigned_to=assigned_to_user_id,
                status='pending',
                priority=priority,
                request_data=epics_data,
                original_data=epics_data,
                created_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24)
            )
            
            session.add(approval)
            session.commit()
            session.refresh(approval)
            
            approval_id = approval.approval_id
            
            logger.info(f"Created epic approval request #{approval_id}")
            
            # Send Telegram notification
            assigned_user = session.query(User).filter(
                User.id == assigned_to_user_id
            ).first()
            
            if assigned_user and assigned_user.telegram_user_id:
                ApprovalService._send_telegram_notification(
                    telegram_user_id=assigned_user.telegram_user_id,
                    telegram_chat_id=assigned_user.telegram_chat_id,
                    approval_id=approval_id
                )
            else:
                logger.warning(f"User {assigned_to_user_id} has no Telegram account linked")
            
            return approval_id
    
    @staticmethod
    def create_story_approval(
        stories_data: Dict[str, Any],
        requested_by_user_id: int,
        assigned_to_user_id: int,
        priority: str = 'normal'
    ) -> int:
        """Create approval request for story creation."""
        with get_session() as session:
            approval = ApprovalRequest(
                request_type='story_creation',
                entity_type='story',
                entity_id=0,
                requested_by=requested_by_user_id,
                assigned_to=assigned_to_user_id,
                status='pending',
                priority=priority,
                request_data=stories_data,
                original_data=stories_data,
                created_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24)
            )
            
            session.add(approval)
            session.commit()
            session.refresh(approval)
            
            approval_id = approval.approval_id
            
            logger.info(f"Created story approval request #{approval_id}")
            
            # Send Telegram notification
            assigned_user = session.query(User).filter(
                User.id == assigned_to_user_id
            ).first()
            
            if assigned_user and assigned_user.telegram_user_id:
                ApprovalService._send_telegram_notification(
                    telegram_user_id=assigned_user.telegram_user_id,
                    telegram_chat_id=assigned_user.telegram_chat_id,
                    approval_id=approval_id
                )
            
            return approval_id
    
    @staticmethod
    def create_sprint_approval(
        sprint_data: Dict[str, Any],
        requested_by_user_id: int,
        assigned_to_user_id: int,
        priority: str = 'high'
    ) -> int:
        """Create approval request for sprint planning."""
        with get_session() as session:
            approval = ApprovalRequest(
                request_type='sprint_planning',
                entity_type='sprint',
                entity_id=0,
                requested_by=requested_by_user_id,
                assigned_to=assigned_to_user_id,
                status='pending',
                priority=priority,
                request_data=sprint_data,
                original_data=sprint_data,
                created_at=datetime.now(timezone.utc),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=24)
            )
            
            session.add(approval)
            session.commit()
            session.refresh(approval)
            
            approval_id = approval.approval_id
            
            logger.info(f"Created sprint approval request #{approval_id}")
            
            # Send Telegram notification
            assigned_user = session.query(User).filter(
                User.id == assigned_to_user_id
            ).first()
            
            if assigned_user and assigned_user.telegram_user_id:
                ApprovalService._send_telegram_notification(
                    telegram_user_id=assigned_user.telegram_user_id,
                    telegram_chat_id=assigned_user.telegram_chat_id,
                    approval_id=approval_id
                )
            
            return approval_id
    
    @staticmethod
    def _send_telegram_notification(
        telegram_user_id: int,
        telegram_chat_id: int,
        approval_id: int
    ):
        """Send Telegram notification for approval request."""
        import asyncio
        from backend.telegram.handlers.approval_handler import send_approval_notification
        
        try:
            # Check if there's already a running event loop
            try:
                loop = asyncio.get_running_loop()
                # We're inside an async context, create a task in a separate thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        send_approval_notification(telegram_user_id, telegram_chat_id, approval_id)
                    )
                    future.result(timeout=10)  # Wait up to 10 seconds
                logger.info(f"Sent Telegram notification for approval #{approval_id}")
            except RuntimeError:
                # No running loop, we can use asyncio.run()
                asyncio.run(
                    send_approval_notification(telegram_user_id, telegram_chat_id, approval_id)
                )
                logger.info(f"Sent Telegram notification for approval #{approval_id}")
        except Exception as e:
            logger.error(f"Failed to send Telegram notification: {e}")
            # Don't fail the pipeline if notification fails
            logger.warning("Pipeline will continue, but manual notification may be needed")
    
    @staticmethod
    def get_pm_user_id() -> Optional[int]:
        """
        Get PM user ID for approval assignment.
        
        Returns first user with 'product_owner' role.
        """
        with get_session() as session:
            from backend.db.models import Role
            
            pm_role = session.query(Role).filter(
                Role.role_name == 'product_owner'
            ).first()
            
            if not pm_role:
                logger.warning("No product_owner role found")
                return None
            
            pm_user = session.query(User).filter(
                User.role_id == pm_role.role_id
            ).first()
            
            if not pm_user:
                logger.warning("No user with product_owner role found")
                return None
            
            return pm_user.id


# Singleton instance
approval_service = ApprovalService()
