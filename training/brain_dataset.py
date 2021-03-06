from typing import Any, Callable, List, Union
from multiprocessing import Manager
from pathlib import Path


from generator_coords import CoordsGenerator
import numpy as np

from torch.utils.data import Dataset

_Path = Union[str, Path]


class BrainDataset(Dataset):
    """General purpose dataset class with several data sources `list_data`."""

    def __init__(
        self,
        shared_dict,
        list_data: List[int],
        list_shape: List[int],
        list_sub_shape: List[int],
        open_fn: Callable,
        dict_transform: Callable = None,
        val_subjects: int = 0,
        mode: str = "train",
        input_key: str = "images",
        output_key: str = "targets",
    ):
        """
        Args:
            list_data (List[Dict]): list of dicts, that stores
                you data annotations,
                (for example path to images, labels, bboxes, etc.)
            list_shape (List[int]):
            list_sub_shape (List[int]):
            open_fn (callable): function, that can open your
                annotations dict and
                transfer it to data, needed by your network
                (for example open image by path, or tokenize read string.)
            dict_transform (callable): transforms to use on dict.
                (for example normalize image, add blur, crop/resize/etc)
        """
        self.val_subjects = val_subjects
        self.shared_dict = shared_dict
        self.data = list_data
        self.open_fn = open_fn
        self.generator = CoordsGenerator(
            list_shape=list_shape, list_sub_shape=list_sub_shape
        )
        self.mode = mode
        self.dict_transform = (
            dict_transform if dict_transform is not None else lambda x: x
        )
        self.input_key = input_key
        self.output_key = output_key
        self.subvolume_shape = np.array(list_sub_shape)
        self.coords = self.generator.get_coordinates(mode=self.mode)
        if self.mode != "train" and self.val_subjects == 0:
            raise ValueError("BrainDatasets cannot have mode!='train' and val_subjects == 0")

    def __len__(self) -> int:
        """
        Returns:
            int: length of the dataset
        """
        if self.mode != "train":
            return len(self.data) * len(self.coords)
        else:
            return len(self.data)

    def __getitem__(self, index: int) -> Any:
        """Gets element of the dataset.
        Args:
            index (int): index of the element in the dataset
        Returns:
            List of elements by index
        """
        if self.mode != "train":
            coords = np.expand_dims(self.coords[(index - 1) // self.val_subjects], 0)
            item = self.data[index // len(self.coords)]
        else:
            item = self.data[index]
            coords = self.coords
        dict_ = self.open_fn(item)

        sample_dict = self.__crop__(dict_, coords)

        return sample_dict

    def __crop__(self, dict_, coords):
        """Get crop of images.
        Args:
            dict_ (List[Dict]): list of dicts, that stores
                you data annotations,
                (for example path to images, labels, bboxes, etc.)
            coords (callable): coords od crops
        Returns:
            crop images
        """
        output = self.shared_dict
        output_labels_list = []
        output_images_list = []
        for start_end in coords:
            for key, dict_key in dict_.items():
                if key == self.input_key:
                    output_images_list.append(
                        np.expand_dims(
                            dict_key[
                                start_end[0][0] : start_end[0][1],
                                start_end[1][0] : start_end[1][1],
                                start_end[2][0] : start_end[2][1],
                            ],
                            0,
                        )
                    )

                elif key == self.output_key:
                    labels = np.expand_dims(
                        dict_key[start_end[0][0] : start_end[0][1],
                                 start_end[1][0] : start_end[1][1],
                                 start_end[2][0] : start_end[2][1],
                                ],
                        0,)

                    output_labels_list.append(labels)

        output_images = np.concatenate(output_images_list)
        output_labels = np.concatenate(output_labels_list)
        output[self.input_key] = output_images
        output[self.output_key] = output_labels.squeeze().astype(np.int64)
        return self.dict_transform(output)
