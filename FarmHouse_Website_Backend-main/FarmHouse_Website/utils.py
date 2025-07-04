import base64
import random
from datetime import datetime, timedelta

from django.core.mail import EmailMessage
from django.db.models import Q
from rest_framework.serializers import Serializer

from FarmHouse_Website_Backend import settings
from . import compressor, views
from .models import Bookings, ReviewsMedia

# # Define payment status constants for clarity
# PAYMENT_STATUS_PENDING = 0
# PAYMENT_STATUS_PAID = 1
# PAYMENT_STATUS_APPROVED_UNPAID = 2

# # List of payment statuses that should block dates (confirmed bookings)
# CONFIRMED_PAYMENT_STATUSES = [PAYMENT_STATUS_PAID, PAYMENT_STATUS_APPROVED_UNPAID]


# def get_available_dates(start_date, end_date=None, days=30):
#     """
#     Get a list of available date ranges between start_date and end_date
#     or next [days] days if end_date is not provided.
#     """
#     if not end_date:
#         end_date = start_date + timedelta(days=days)

#     # Get all confirmed bookings in the date range
#     bookings = Bookings.objects.filter(
#         Q(paymentStatus__in=CONFIRMED_PAYMENT_STATUSES) &
#         (
#                 (Q(checkInDate__gte=start_date) & Q(checkInDate__lte=end_date)) |
#                 (Q(checkOutDate__gte=start_date) & Q(checkOutDate__lte=end_date)) |
#                 (Q(checkInDate__lte=start_date) & Q(checkOutDate__gte=end_date))
#         )
#     ).order_by('checkInDate')

#     # If no bookings, the whole period is available
#     if not bookings:
#         return [{'start': start_date, 'end': end_date}]

#     available_periods = []
#     current_date = start_date

#     # Add periods between bookings
#     for booking in bookings:
#         if current_date < booking.checkInDate:
#             available_periods.append({
#                 'start': current_date,
#                 'end': booking.checkInDate - timedelta(days=1)
#             })
#         current_date = booking.checkOutDate + timedelta(days=1)

#     # Add period after the last booking
#     if current_date <= end_date:
#         available_periods.append({
#             'start': current_date,
#             'end': end_date
#         })

#     return available_periods


def check_booking_availability(check_in_date, check_out_date, exclude_booking_id=None):
    """
    Check if dates are available for booking.
    Returns (is_available: bool, conflicting_bookings: QuerySet)
    """
    # Look for any confirmed bookings that overlap with the requested period
    conflicts_query = Bookings.objects.filter(
        Q(paymentStatus="PAID") &
        (
            # Case 1: A booking that starts during the requested period
                (Q(checkInDate__gte=check_in_date) & Q(checkInDate__lt=check_out_date)) |
                # Case 2: A booking that ends during the requested period
                (Q(checkOutDate__gt=check_in_date) & Q(checkOutDate__lte=check_out_date)) |
                # Case 3: A booking that completely spans the requested period
                (Q(checkInDate__lte=check_in_date) & Q(checkOutDate__gte=check_out_date))
        )
    )

    # Exclude current booking if updating existing booking
    if exclude_booking_id:
        conflicts_query = conflicts_query.exclude(bookingId=exclude_booking_id)

    conflicts = []

    for booking in conflicts_query.order_by('checkInDate'):
        conflicts.append({
            'start': booking.checkInDate,
            'end': booking.checkOutDate
        })

    return len(conflicts) != 0, conflicts


# def generate_alternative_dates(check_in_date, check_out_date, duration):
#     """
#     Generate alternative date suggestions when requested dates are unavailable.
#     Returns dictionary with partial_availability and next_available_periods.
#     """
#     alternatives = {
#         'partial_availability': [],  # Periods within requested timeframe (even if shorter)
#         'next_available_periods': []  # Future periods of similar duration
#     }

#     # Get conflicting bookings
#     _, conflicts = check_booking_availability(check_in_date, check_out_date)

#     if not conflicts.count != 0:
#         return alternatives

#     # 1. Find available periods within the requested timeframe (even if partial)
#     current_date = check_in_date
#     for booking in conflicts:
#         if current_date < booking['start']:
#             available_days = (booking['start'] - current_date).days
#             # Include even if it's shorter than requested
#             if available_days >= 1:
#                 alternatives['partial_availability'].append({
#                     'start_date': current_date.strftime('%Y-%m-%d'),
#                     'end_date': (booking['start'] - timedelta(days=1)).strftime('%Y-%m-%d'),
#                     'days': available_days
#                 })
#         current_date = max(current_date, booking['end'] + timedelta(days=1))

#     if current_date < check_out_date:
#         available_days = (check_out_date - current_date).days
#         if available_days >= 1:
#             alternatives['partial_availability'].append({
#                 'start_date': current_date.strftime('%Y-%m-%d'),
#                 'end_date': check_out_date.strftime('%Y-%m-%d'),
#                 'days': available_days
#             })

#     # 2. Find next available periods for the same or similar duration
#     # Start looking from the day after the last conflict ends
#     latest_conflict = conflicts[len(conflicts) - 1]
#     search_start = latest_conflict['end'] + timedelta(days=1)
#     search_end = search_start + timedelta(days=90)  # Look 90 days ahead

#     available_periods = get_available_dates(search_start, search_end)

#     # Find periods that are at least 50% of the requested duration
#     min_acceptable_duration = max(2, duration // 2)  # At least 2 days or half the requested duration

#     for period in available_periods:
#         period_duration = (period['end'] - period['start']).days + 1

#         # If period is exactly the requested duration, add it directly
#         if period_duration == duration:
#             alternatives['next_available_periods'].append({
#                 'start_date': period['start'].strftime('%Y-%m-%d'),
#                 'end_date': period['end'].strftime('%Y-%m-%d'),
#                 'days': period_duration
#             })

#         # If period is longer than needed, offer multiple options
#         elif period_duration > duration:
#             for i in range(0, min(5, period_duration - duration + 1), 1):
#                 start = period['start'] + timedelta(days=i)
#                 end = start + timedelta(days=duration - 1)

#                 alternatives['next_available_periods'].append({
#                     'start_date': start.strftime('%Y-%m-%d'),
#                     'end_date': end.strftime('%Y-%m-%d'),
#                     'days': duration
#                 })

#         # If period is shorter but at least the minimum acceptable duration
#         elif period_duration >= min_acceptable_duration:
#             alternatives['next_available_periods'].append({
#                 'start_date': period['start'].strftime('%Y-%m-%d'),
#                 'end_date': period['end'].strftime('%Y-%m-%d'),
#                 'days': period_duration
#             })

#         # Limit to 10 total alternatives
#         if len(alternatives['next_available_periods']) >= 10:
#             break

#     # Sort alternatives by days (highest first)
#     alternatives['partial_availability'].sort(key=lambda x: x['days'], reverse=True)
#     alternatives['next_available_periods'].sort(key=lambda x: x['days'], reverse=True)

#     return alternatives


def validate_booking_dates(check_in_date, check_out_date):
    """
    Validate booking dates for basic business rules.
    Returns (is_valid: bool, error_message: str)
    """
    try:
        if isinstance(check_in_date, str):
            check_in_date = datetime.strptime(check_in_date, '%Y-%m-%d').date()
        if isinstance(check_out_date, str):
            check_out_date = datetime.strptime(check_out_date, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return False, 'Invalid date format. Please use YYYY-MM-DD.'

    today = datetime.now().date()

    # Check if check-in date is in the past
    if check_in_date < today:
        return False, 'Check-in date cannot be in the past.'

    # Check if check-out date is after check-in date
    if check_out_date < check_in_date:
        return False, 'Check-out date must be after check-in date.'

    # Check if booking duration is reasonable (e.g., max 30 days)
    duration = (check_out_date - check_in_date).days
    if duration > 30:
        return False, 'Maximum booking duration is 30 days.'

    # Check if booking is too far in the future (e.g., max 1 year ahead)
    max_future_date = today + timedelta(days=365)
    if check_in_date > max_future_date:
        return False, 'Bookings can only be made up to 1 year in advance.'

    return True, 'Booking dates are valid'


# def get_availability_info(check_in_date, check_out_date):
#     """
#     Get availability information for given date range.
#     Returns availability status and alternatives if unavailable.
#     """
#     try:
#         if isinstance(check_in_date, str):
#             check_in_date = datetime.strptime(check_in_date, '%Y-%m-%d').date()
#         if isinstance(check_out_date, str):
#             check_out_date = datetime.strptime(check_out_date, '%Y-%m-%d').date()

#         duration = (check_out_date - check_in_date).days
#     except (ValueError, TypeError):
#         return False, None, 'Invalid date format. Please use YYYY-MM-DD.'

#     is_available, _ = check_booking_availability(check_in_date, check_out_date)
#     alternatives = None

#     if not is_available:
#         alternatives = generate_alternative_dates(check_in_date, check_out_date, duration)

#     return True, {
#         'available': is_available,
#         'requested_period': {
#             'start_date': check_in_date.strftime('%Y-%m-%d'),
#             'end_date': check_out_date.strftime('%Y-%m-%d'),
#             'days': duration
#         },
#         'alternative_dates': alternatives
#     }, None


def get_encoded_media(media):
    encoded_media = None

    if media.name.endswith('.jpg') or media.name.endswith('.png') or media.name.endswith('.jpeg'):
        if media.size >= settings.MAX_UPLOAD_SIZE():
            encoded_media = compressor.compressImageWithBestQuality(media.read())
        else:
            encoded_media = media.read()
    elif media.name.endswith('.mp4'):
        if media.size >= settings.MAX_UPLOAD_SIZE():
            encoded_media = compressor.compressVideo(media.read())
        else:
            encoded_media = media.read()

    return encoded_media


def setMedia(media_list, review):
    try:
        for media in media_list:
            ReviewsMedia.objects.create(reviewId=review, mediaType=media.content_type, media=get_encoded_media(media), mediaName = media.name)

        return True
    except Exception as e:
        print(e)
        return False

def getMedia(review_id):
    media_list = []
    try:
        media_entries = ReviewsMedia.objects.filter(reviewId=review_id)
        for media_entry in media_entries:
            media_list.append(
                {
                    'media_name' : media_entry.mediaName,
                    'media_type': media_entry.mediaType,
                    'media' : base64.b64encode(media_entry.media).decode('utf-8')
                }
            )
    except Exception as e:
        print(e)
        media_list.append('Some error occured.')
    finally:
        return media_list


def sendConfirmationEmail(receiver, name, checkin, checkout):

    try:
        print("Sending to:", receiver)

        email = EmailMessage(
            subject="🏨 Booking Confirmation – Nirmal Farms",
            body=f""""Dear {name},

                    We are delighted to inform you that your booking at Nirmal Farms has been successfully confirmed! 🌿

                    Your stay is reserved from {checkin} to {checkout} under the name {name}.

                    We truly look forward to hosting you and ensuring you have a relaxing and memorable experience amidst nature and comfort.

                    If you have any special requests or questions before your arrival, feel free to reach out to us.

                    Welcome to Nirmal Farms — your peaceful getaway awaits!

                    Warm regards,
                    The Nirmal Farms Team
                    📞 xxxxxxxxxxx
                    📧 xxxxxxxxxxx""",
            from_email=settings.EMAIL_HOST_USER,
            to=[receiver]
        )
        
        if email.send(fail_silently=False) :
            print("email sent")
            return True
        
        return False
    except Exception as e:
        print(e)
