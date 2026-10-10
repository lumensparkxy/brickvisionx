"""Release authority is a verified Google principal, never user-supplied actor metadata."""
from dataclasses import dataclass

APPROVER = 'maswadkar@gmail.com'


@dataclass(frozen=True)
class GoogleIdentity:
    email: str
    subject: str
    verified: bool

    def require_approver(self):
        if not self.verified or self.email != APPROVER or not self.subject:
            raise PermissionError('Authenticated tutorial approver required')


def verify_google_identity(token: str) -> GoogleIdentity:
    from google.auth.transport.requests import Request
    from google.oauth2.id_token import verify_oauth2_token
    claims = verify_oauth2_token(token, Request(), audience='32555940559.apps.googleusercontent.com')
    if claims.get('iss') not in ('accounts.google.com', 'https://accounts.google.com'):
        raise PermissionError('Unexpected identity issuer')
    identity = GoogleIdentity(email=claims.get('email', ''), subject=claims.get('sub', ''),
                              verified=claims.get('email_verified') is True)
    identity.require_approver()
    return identity


def role_credentials(project: str, role: str):
    if role not in ('uploader', 'publisher'):
        raise ValueError('Unknown release role')
    import google.auth
    from google.auth import impersonated_credentials
    source, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
    return impersonated_credentials.Credentials(source_credentials=source,
        target_principal=f'guide2build-{role}@{project}.iam.gserviceaccount.com',
        target_scopes=['https://www.googleapis.com/auth/cloud-platform'], lifetime=900)
