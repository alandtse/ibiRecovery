# Disk Analysis and Recovery Methodology

This document details the technical process used to analyze and mount the Sandisk Ibi device for data recovery.

## 🧭 Disk Analysis and Mounting Strategy

The recovery process began with a full disk image obtained from a Sandisk Ibi device. Using tools like `testdisk`, the partition table was analyzed to detect possible partitions. Multiple partitions were identified, but only the last one—a large ext4 volume—contained real file data and ibi-specific structures.

This partition started at sector 1,725,440 and was mounted via a loopback device using the calculated offset. Successful mounting was confirmed by the presence of the `restsdk/` and `restsdk-info/` folders. The large ext4 partition, approximately 459 GiB in size, was found to hold the content database along with all file blobs.

This initial disk analysis and mounting strategy guided all subsequent analysis and database querying efforts.

## 🔧 Partition Table Type Selection

### ⚠ GPT vs Intel Partition Scheme

When initially analyzing the disk image, `testdisk` detected the presence of a protective MBR (PMBR) with a `0xEE` partition type:

```plaintext
The partition type 0xEE (as seen on /dev/disk6s1) is a protective MBR (PMBR) used to indicate that the disk is using the GUID Partition Table (GPT) scheme.
```

This is common for GPT-formatted disks. The `0xEE` entry spans the entire disk and exists to warn legacy tools not to overwrite the GPT layout.

However, no usable partitions were found when proceeding with the default GPT mode. Switching to the **Intel/PC partition type** in `testdisk` was necessary. This revealed multiple deleted partitions, including the final large ext4 volume that contained the actual ibi data.

This suggests the disk may use a hybrid layout or corrupted GPT that misleads recovery tools unless manually overridden.

## 🧾 TestDisk Output Snapshot

The following is the original output from `testdisk` after scanning the disk:

```plaintext
Disk /dev/sdc - 500 GB / 465 GiB - CHS 7600 255 63
     Partition               Start        End    Size in sectors
>D Linux                    3 226 32    16 162 18     204800 [system]
 D Linux                   16 162 19    29  98  5     204800
 D Linux                   29  98  6    42  33 55     204800
 D Linux                   42  33 56    74 195 57     524288
 D Linux Swap              74 195 58   107 102 59     524288
 D Linux                  107 102 60  7600  45 61  120371456
```

- Partition 6 (marked `D Linux`) was the final and largest entry, spanning over 120 million sectors.
- This corresponded to a partition size of approximately 459 GiB.
- This partition was selected for mounting and recovery based on its size and location.

## 💾 Mounting Process

```bash
sudo mount -o ro,loop,offset=$((10710260 * 512)) /path/to/disk.img /mnt/recovered
```

- Mounting revealed the presence of ibi-specific directories (`restsdk/`, `restsdk-info/`), confirming it as the main data partition.

## 🔍 Key Findings

1. **Partition Layout**: The device uses a complex partition scheme with multiple small system partitions and one large data partition
2. **File System**: ext4 file system containing the main data
3. **Structure**: Standard Linux directory structure with ibi-specific folders in `/restsdk/`
4. **Database Location**: Primary database found at `/restsdk/data/db/index.db`
5. **File Storage**: Files organized under `/restsdk/data/files/` using contentID-based directory structure

## 🛠️ Tools Used

- **testdisk**: For partition discovery and analysis
- **mount**: For mounting the recovered partition
- **dd/ddrescue**: For creating the initial disk image
- **file**: For identifying file systems and partition types

## 📚 References

- **[Complete Schema Documentation](schema_documentation.md)** - Database structure discovered after mounting
- **[API Specification](api_specification.json)** - Machine-readable format based on this analysis
- **[Metadata Strategy](metadata_strategy.md)** - Data preservation decisions based on findings

---

This methodology can be adapted for other ibi device recoveries or similar embedded Linux storage devices.
