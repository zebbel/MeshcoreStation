"""Transport-independent reply splitting and accepted-part accounting."""
import asyncio
from dataclasses import dataclass, field
from .templates import split_reply


@dataclass
class ReplyDelivery:
    accepted: list = field(default_factory=list)
    status: str = 'processing'

    @property
    def text(self):
        return ''.join(self.accepted)

    async def deliver(self, reply, send):
        """send(part) returns accepted text, or None if delivery was rejected.

        Acceptance means radio submission or local room storage, not RF receipt.
        A transport can return replacement text and stop further delivery.
        """
        if not reply:
            self.status = 'no reply'
            return
        try:
            for part in split_reply(reply):
                if self.accepted:
                    await asyncio.sleep(1)
                accepted = await send(part)
                if accepted is None:
                    self.status = 'partial' if self.accepted else 'failed'
                    return
                self.accepted.append(accepted)
                if accepted != part:
                    self.status = 'partial'
                    return
            self.status = 'completed'
        except BaseException:
            self.status = 'partial' if self.accepted else 'failed'
            raise

    def failed(self):
        self.status = 'partial' if self.accepted else 'failed'
