from typing import Optional, List


class LayerPublicationStatus:
    def __init__(
        self,
        is_container: bool,
        original_name: str,
        layer_name: str,
        exception: Optional[str],
        datatype: str,
        timestamps: List[str],
    ):
        self.is_container: bool = is_container
        self.original_name: str = original_name
        self.layer_name: str = layer_name
        self.exception: Optional[str] = exception
        self.datatype: str = datatype
        self.timestamps: List[str] = timestamps

    @property
    def success(self):
        return self.exception is None

    @property
    def is_layer(self):
        return not self.is_container
