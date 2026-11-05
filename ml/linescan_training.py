"""Explicit epoch history independent of YOLOX's inline evaluation interval."""


def history_trainer(base):
    class HistoryTrainer(base):
        def after_epoch(self):
            super().after_epoch()
            if self.rank == 0 and self.epoch + 1 in (2, 4, 6, 8):
                self.save_ckpt(f"epoch_{self.epoch + 1}")

    return HistoryTrainer
