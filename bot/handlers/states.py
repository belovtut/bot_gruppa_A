"""FSM state definitions for all bot flows."""
from aiogram.fsm.state import State, StatesGroup


class BroadcastStates(StatesGroup):
    """Broadcast message to all users."""
    waiting_for_message = State()


class FilterStates(StatesGroup):
    """Controller search / filter flow (browse & invite modes)."""
    active = State()               # Callback-driven filter browsing
    entering_date = State()        # Waiting for date text


class InviteStates(StatesGroup):
    """Event creation & invitation sending."""
    selecting = State()            # Selecting controllers from results
    entering_random_count = State()
    entering_title = State()
    entering_date = State()
    entering_time = State()
    entering_location = State()
    entering_rate = State()
    entering_dress_code = State()
    entering_task = State()
    confirming = State()


class ProfileStates(StatesGroup):
    """Controller self-registration / profile update."""
    entering_name = State()
    entering_birth_date = State()
    entering_phone = State()
    choosing_specializations = State()
    choosing_experience = State()
    choosing_areas = State()
    choosing_languages = State()
    confirming = State()


class AddControllerStates(StatesGroup):
    """Admin adding a controller."""
    entering_username = State()
    entering_name = State()
    entering_birth_date = State()
    entering_phone = State()
    choosing_specializations = State()
    choosing_experience = State()
    entering_location = State()
    choosing_areas = State()
    choosing_languages = State()
    entering_rating = State()
    confirming = State()


class DeclineCommentStates(StatesGroup):
    """Candidate entering custom decline comment."""
    entering_comment = State()


class StaffApplicationAdminStates(StatesGroup):
    """Admin interactions with staff applications."""
    entering_message = State()


class StaffApplicationCandidateStates(StatesGroup):
    """Candidate reply flow for admin messages on application."""
    entering_message = State()


class ControllerEditStates(StatesGroup):
    """Admin editing existing controller profile fields."""
    entering_value = State()
