#!/usr/bin/python

# written by sqall
# twitter: https://twitter.com/sqall01
# blog: http://blog.h4des.org
# github: https://github.com/sqall01
#
# Licensed under the GNU Public License, version 2.

import binascii
import struct
import sys
import hashlib
from Elf import ElfN_Ehdr, Shstrndx, ElfN_Shdr, SH_flags, SH_type, \
	Elf32_Phdr, P_type, P_flags, D_tag, ElfN_Dyn, \
	ElfN_Rel, ElfN_Rela, ElfN_Sym, R_type, \
	Section, Segment, DynamicSymbol


class ElfParser(object):

	def __init__(self, filename, force=False, startOffset=0,
			forceDynSymParsing=0, onlyParseHeader=False):
		self.forceDynSymParsing = forceDynSymParsing
		self.header = None
		self.segments = list()
		self.sections = list()
		self.fileParsed = False
		self.dynamicSymbolEntries = list()
		self.dynamicSegmentEntries = list()
		self.jumpRelocationEntries = list()
		self.relocationEntries = list()
		self.startOffset = startOffset
		self.data = bytearray()
		self.bits = 0

		# read file and convert data to list
		f = open(filename, "rb")
		f.seek(self.startOffset, 0)
		self.data = bytearray(f.read())
		f.close()

		# parse ELF file
		self.parseElf(self.data, onlyParseHeader=onlyParseHeader)

		# check if parsed ELF file and new generated one are the same
		if self.fileParsed is True and force is False:
			# generate md5 hash of file that was parsed
			tempHash = hashlib.md5()
			tempHash.update(self.data)
			oldFileHash = tempHash.digest()

			# generate md5 hash of file that was newly generated
			tempHash = hashlib.md5()
			tempHash.update(self.generateElf())
			newFileHash = tempHash.digest()

			if oldFileHash != newFileHash:
				raise NotImplementedError('Not able to parse and ' \
					+ 're-generate ELF file correctly. This can happen '\
					+ 'when the ELF file is parsed out of an other file '\
					+ 'like a core dump. Use "force=True" to ignore this '\
					+ 'check.')

	# this function interprets the r_info field from ElfN_Rel(a) structs
	# depending on self.bits
	def relocationSymIdxAndTypeFromInfo(self, rInfo):
		if self.bits == 32:
			rSym = (rInfo >> 8)
			rType = (rInfo & 0xff)
		elif self.bits == 64:
			rSym = (rInfo >> 32)
			rType = (rInfo & 0xffffffff)
		return (rSym, rType)


	# this function converts a section header entry to a list of data
	# return values: (bytearray) converted section header entry
	def sectionHeaderEntryToBytearray(self, sectionHeaderEntryToWrite):
		if self.bits == 32:
			structFormat = '< 2I 4I 2I 2I'
		elif self.bits == 64:
			structFormat = '< 2I 4Q 2I 2Q'

		sectionHeaderEntryRaw = bytearray(struct.pack(structFormat,
			# uint32_t   sh_name;
			sectionHeaderEntryToWrite.sh_name,
			# uint32_t   sh_type;
			sectionHeaderEntryToWrite.sh_type,
			# uintN_t    sh_flags;     (N = 32/64)
			sectionHeaderEntryToWrite.sh_flags,
			# ElfN_Addr  sh_addr;      (N = 32/64)
			sectionHeaderEntryToWrite.sh_addr,
			# ElfN_Off   sh_offset;    (N = 32/64)
			sectionHeaderEntryToWrite.sh_offset,
			# uintN_t    sh_size;      (N = 32/64)
			sectionHeaderEntryToWrite.sh_size,
			# uint32_t   sh_link;
			sectionHeaderEntryToWrite.sh_link,
			# uint32_t   sh_info;
			sectionHeaderEntryToWrite.sh_info,
			# uintN_t    sh_addralign; (N = 32/64)
			sectionHeaderEntryToWrite.sh_addralign,
			# uintN_t    sh_entsize;   (N = 32/64)
			sectionHeaderEntryToWrite.sh_entsize,
		))

		return sectionHeaderEntryRaw


	# this function generates a new section
	# return values: (Section) new generated section
	def generateNewSection(self, sectionName, sh_name, sh_type, sh_flags,
		sh_addr, sh_offset, sh_size, sh_link, sh_info, sh_addralign,
		sh_entsize):
		newsection = Section()

		newsection.sectionName = sectionName

		'''
		uint32_t   sh_name;
		'''
		newsection.elfN_shdr.sh_name = sh_name

		'''
		uint32_t   sh_type;
		'''
		newsection.elfN_shdr.sh_type = sh_type

		'''
		uintN_t    sh_flags;        (N = 32/64)
		'''
		newsection.elfN_shdr.sh_flags = sh_flags

		'''
		ElfN_Addr  sh_addr;         (N = 32/64)
		'''
		newsection.elfN_shdr.sh_addr = sh_addr

		'''
		ElfN_Off  sh_offset;        (N = 32/64)
		'''
		newsection.elfN_shdr.sh_offset = sh_offset

		'''
		uintN_t    sh_size;         (N = 32/64)
		'''
		newsection.elfN_shdr.sh_size = sh_size

		'''
		uint32_t   sh_link;
		'''
		newsection.elfN_shdr.sh_link = sh_link

		'''
		uint32_t   sh_info;
		'''
		newsection.elfN_shdr.sh_info = sh_info

		'''
		uintN_t    sh_addralign;    (N = 32/64)
		'''
		newsection.elfN_shdr.sh_addralign = sh_addralign

		'''
		uintN_t    sh_entsize;      (N = 32/64)
		'''
		newsection.elfN_shdr.sh_entsize = sh_entsize

		return newsection


	# this function parses a dynamic symbol at the given offset
	# return values: (DynamicSymbol) the parsed dynamic symbol
	def _parseDynamicSymbol(self, offset, stringTableOffset, stringTableSize):

		# check if the file was completely parsed before
		if self.fileParsed is False:
			raise ValueError("Operation not possible. " \
				+ "File was not completely parsed before.")

		tempSymbol = DynamicSymbol()

		# get values from the symbol table
		"""
		typedef struct {
			uint32_t      st_name;
			Elf32_Addr    st_value;  // *
			uint32_t      st_size;   // *
			unsigned char st_info;
			unsigned char st_other;
			uint16_t      st_shndx;
		} Elf32_Sym;

		typedef struct {
			uint32_t      st_name;
			unsigned char st_info;
			unsigned char st_other;
			uint16_t      st_shndx;
			Elf64_Addr    st_value;  // *
			uint64_t      st_size;   // *
		} Elf64_Sym;

		Difference: order (*)
		"""
		if self.bits == 32:
			fmt = '<I II BBH'
			fmtSize = struct.calcsize(fmt)
			(
				tempSymbol.ElfN_Sym.st_name,
				tempSymbol.ElfN_Sym.st_value,   # *
				tempSymbol.ElfN_Sym.st_size,    # *
				tempSymbol.ElfN_Sym.st_info,
				tempSymbol.ElfN_Sym.st_other,
				tempSymbol.ElfN_Sym.st_shndx,
			) = struct.unpack(fmt, self.data[offset:offset+fmtSize])
		elif self.bits == 64:
			fmt = '<I BBH QQ'
			fmtSize = struct.calcsize(fmt)
			(
				tempSymbol.ElfN_Sym.st_name,
				tempSymbol.ElfN_Sym.st_info,
				tempSymbol.ElfN_Sym.st_other,
				tempSymbol.ElfN_Sym.st_shndx,
				tempSymbol.ElfN_Sym.st_value,   # *
				tempSymbol.ElfN_Sym.st_size,    # *
			) = struct.unpack(fmt, self.data[offset:offset+fmtSize])

		# extract name from the string table
		nStart = stringTableOffset + tempSymbol.ElfN_Sym.st_name
		nMaxEnd = stringTableOffset + stringTableSize
		nEnd = self.data.find('\x00', nStart, nMaxEnd)
		# use empty string if string is not terminated (nEnd == -1)
		nEnd = max(nStart, nEnd)
		tempSymbol.symbolName = bytes(self.data[nStart:nEnd])

		# return dynamic symbol
		return tempSymbol


	# this function writes a dynamic symbol to a given offset
	# return values: None
	def _writeDynamicSymbol(self, data, offset, elfSymbol):
		if self.bits == 32:
			fmt = '< I II BBH'
			fmtSize = struct.calcsize(fmt)
			assert fmtSize == 16

			data[offset:offset+fmtSize] = struct.pack(fmt,
				elfSymbol.st_name,
				elfSymbol.st_value, # *
				elfSymbol.st_size,  # *
				elfSymbol.st_info,
				elfSymbol.st_other,
				elfSymbol.st_shndx,
			)
		elif self.bits == 64:
			fmt = '<I BBH QQ'
			fmtSize = struct.calcsize(fmt)
			assert fmtSize == 24

			data[offset:offset+fmtSize] = struct.pack(fmt,
				elfSymbol.st_name,
				elfSymbol.st_info,
				elfSymbol.st_other,
				elfSymbol.st_shndx,
				elfSymbol.st_value, # *
				elfSymbol.st_size,  # *
			)


	# this function parses the ELF file
	# return values: None
	def parseElf(self, buffer_list, onlyParseHeader=False):

		# large enough to contain e_ident?
		if len(buffer_list) < 16:
			raise ValueError("Buffer is too small to contain an ELF header.")

		###############################################
		# parse ELF header

		'''
		The ELF header is described by the type Elf32_Ehdr or Elf64_Ehdr:

		#define EI_NIDENT 16

		typedef struct {
			unsigned char e_ident[EI_NIDENT];
			uint16_t      e_type;
			uint16_t      e_machine;
			uint32_t      e_version;
			ElfN_Addr     e_entry;
			ElfN_Off      e_phoff;
			ElfN_Off      e_shoff;
			uint32_t      e_flags;
			uint16_t      e_ehsize;
			uint16_t      e_phentsize;
			uint16_t      e_phnum;
			uint16_t      e_shentsize;
			uint16_t      e_shnum;
			uint16_t      e_shstrndx;
		} ElfN_Ehdr;
		'''


		self.header = ElfN_Ehdr()

		'''
		#define EI_NIDENT 16
		unsigned char e_ident[EI_NIDENT];

		The first 4 bytes of the magic number. These bytes must be:
		EI_MAG0, EI_MAG1, EI_MAG2, EI_MAG3 == 0x7f, 'E', 'L', 'F'

		The fifth byte identifies the architecture for this binary
		'''

		self.header.e_ident = buffer_list[0:16]

		if self.header.e_ident[0:4] != b'\x7fELF':
			raise NotImplementedError("First 4 bytes do not have magic value")


		if self.header.e_ident[4] == ElfN_Ehdr.EI_CLASS.ELFCLASS32:
			self.bits = 32
		elif self.header.e_ident[4] == ElfN_Ehdr.EI_CLASS.ELFCLASS64:
			self.bits = 64
		elif self.header.e_ident[4] == ElfN_Ehdr.EI_CLASS.ELFCLASSNONE:
			raise NotImplementedError("ELFCLASSNONE: This class is invalid.")
		else:
			raise NotImplementedError("Invalid ELFCLASS (e_ident[4]).")

		if (self.bits == 32 and len(buffer_list) < 52) \
		or (self.bits == 64 and len(buffer_list) < 64):
			raise ValueError("Buffer is too small to contain an ELF header.")


		'''
		uint16_t      e_type;

		This member of the structure identifies the object file type.


		uint16_t      e_machine;

		This member specifies the required architecture for an individual file.


		uint32_t      e_version;

		This member identifies the file version:

		EV_NONE     Invalid version.
		EV_CURRENT  Current version.


		ElfN_Addr     e_entry;      (32/64 bit!)

		This member gives the virtual address to which the system first
		transfers control, thus starting the process. If the file has no
		associated entry point, this member holds zero.


		ElfN_Off      e_phoff;      (32/64 bit!)

		This  member holds the program header table's file offset in bytes.
		If the file has no program header table, this member holds zero.


		ElfN_Off      e_shoff;      (32/64 bit!)

		This member holds the section header table's file offset in bytes
		(from the beginning of the file).  If the file has no section header
		table this member holds zero.


		uint32_t      e_flags;

		This member holds processor-specific flags associated with the file.
		Flag names take the form EF_`machine_flag'. Currently no flags have
		been defined.


		uint16_t      e_ehsize;

		This member holds the ELF header's size in bytes.


		uint16_t      e_phentsize;

		This member holds the size in bytes of one entry in the file's
		program header table; all entries are the same size.


		uint16_t      e_phnum;

		This member holds the number of entries in the program header table.
		Thus the product of e_phentsize and e_phnum gives the table's size
		in bytes. If a file has no program header,
		e_phnum holds the value zero.

		If  the  number  of  entries in the program header table is
		larger than or equal to PN_XNUM (0xffff), this member holds
		PN_XNUM (0xffff) and the real number of entries in the program
		header table is held in the sh_info member of  the  initial
		entry in section header table.  Otherwise, the sh_info member of
		the initial entry contains the value zero.

		PN_XNUM  This  is defined as 0xffff, the largest number e_phnum can
		have, specifying where the actual number of program headers
		is assigned.


		uint16_t      e_shentsize;

		This member holds a sections header's size in bytes.  A section
		header is one entry in the section  header  table;  all
		entries are the same size.


		uint16_t      e_shnum;

		This member holds the number of entries in the section header table.
		Thus the product of e_shentsize and e_shnum gives the section
		header table's size in bytes.  If a file has no section header table,
		e_shnum holds the value of zero.

		If the number of entries in the section header table is larger than or
		equal to SHN_LORESERVE (0xff00),  e_shnum  holds
		the  value zero and the real number of entries in the section
		header table is held in the sh_size member of the initial
		entry in section header table.  Otherwise, the sh_size member of
		the initial entry in the section  header  table  holds
		the value zero.


		uint16_t      e_shstrndx;

		This  member  holds  the section header table index of the entry
		associated with the section name string table.  If the
		file has no section name string table, this member holds
		the value SHN_UNDEF.

		If the index of section name string table section is larger than
		or equal to SHN_LORESERVE (0xff00), this member  holds
		SHN_XINDEX  (0xffff)  and  the real index of the section name
		string table section is held in the sh_link member of the
		initial entry in section header table.  Otherwise, the sh_link
		member of the initial entry in section header table contains
		the value zero.
		'''

		if self.bits == 32:
			unpackedHeader = struct.unpack('< 2H I 3I I 6H', buffer_list[16:52])
		elif self.bits == 64:
			unpackedHeader = struct.unpack('< 2H I 3Q I 6H', buffer_list[16:64])

		(
				self.header.e_type,
				self.header.e_machine,
				self.header.e_version,
				self.header.e_entry,    # 32/64 bit!
				self.header.e_phoff,    # 32/64 bit!
				self.header.e_shoff,    # 32/64 bit!
				self.header.e_flags,
				self.header.e_ehsize,
				self.header.e_phentsize,
				self.header.e_phnum,
				self.header.e_shentsize,
				self.header.e_shnum,
				self.header.e_shstrndx,
		) = unpackedHeader


		###############################################
		# check if ELF is supported

		'''
		The sixth byte specifies the data encoding of the
		processor-specific data in the file.
		'''
		if self.header.e_ident[5] == ElfN_Ehdr.EI_DATA.ELFDATANONE:
			raise NotImplementedError("ELFDATANONE: Unknown data format.")
		elif self.header.e_ident[5] == ElfN_Ehdr.EI_DATA.ELFDATA2MSB:
			raise NotImplementedError("ELFDATA2MSB: Not yet supported.")
		elif self.header.e_ident[5] != ElfN_Ehdr.EI_DATA.ELFDATA2LSB:
			raise NotImplementedError("Unknown data format.")


		'''
		The version number of the ELF specification
		'''
		if self.header.e_ident[6] == ElfN_Ehdr.EI_VERSION.EV_NONE:
			raise NotImplementedError("EV_NONE: Invalid version.")
		elif self.header.e_ident[6] != ElfN_Ehdr.EI_VERSION.EV_CURRENT:
			raise NotImplementedError("Invalid version.")


		'''
		This  byte  identifies  the operating system and ABI to which the
		object is targeted.  Some fields in other ELF structures have flags
		and values that have platform-specific  meanings;  the
		interpretation  of  those fields is determined by the value of
		this byte.
		'''
		if not (self.header.e_ident[7] == ElfN_Ehdr.EI_OSABI.ELFOSABI_NONE
			or
			self.header.e_ident[7] == ElfN_Ehdr.EI_OSABI.ELFOSABI_LINUX):
			raise NotImplementedError("EI_OSABI not yet supported")


		'''
		This byte identifies the version of the ABI to which the object is
		targeted.  This field is used to distinguish among incompatible
		versions of an ABI.  The interpretation of this version number is
		dependent on the ABI identified by the EI_OSABI field. Applications
		conforming to this specification use the value 0.
		'''
		if self.header.e_ident[8] != 0:
			raise NotImplementedError("EI_ABIVERSION not yet supported")


		# check if e_type is supported at the moment
		if not (self.header.e_type == ElfN_Ehdr.E_type.ET_EXEC
			or self.header.e_type == ElfN_Ehdr.E_type.ET_DYN):
			raise NotImplementedError("Only e_type ET_EXEC and ET_DYN " \
				+ "are supported yet")


		# check if e_machine is supported at the moment
		expectedMachine = {
				32: ElfN_Ehdr.E_machine.EM_386,
				64: ElfN_Ehdr.E_machine.EM_X86_64,
		}[self.bits]

		if self.header.e_machine != expectedMachine:
			try:
				EM = ElfN_Ehdr.E_machine.reverse_lookup[self.header.e_machine]
			except KeyError:
				EM = hex(self.header.e_machine)
			raise NotImplementedError("Only e_machine EM_386 for ELFCLASS32" \
					+ " and EM_X86_64 for ELFCLASS64 are supported yet" \
					+ " (file has {})".format(EM))


		# check if only the header of the ELF file should be parsed
		# for example to speed up the process for checking if a list of files
		# are valid ELF files
		if onlyParseHeader is True:
			return

		# mark file as completely parsed (actually it is just parsing
		# but without this flag internal functions will not work)
		self.fileParsed = True


		###############################################
		# parse section header table

		'''
		The section header has the following structure:

		typedef struct {               // differences in ELF64:
			uint32_t   sh_name;
			uint32_t   sh_type;
			uint32_t   sh_flags;       //     uint64_t
			Elf32_Addr sh_addr;        //     Elf64_Addr
			Elf32_Off  sh_offset;      //     Elf64_Off
			uint32_t   sh_size;        //     uint64_t
			uint32_t   sh_link;
			uint32_t   sh_info;
			uint32_t   sh_addralign;   //     uint64_t
			uint32_t   sh_entsize;     //     uint64_t
		} Elf32_Shdr;                  // } Elf64_Shdr;
		'''

		# create a list of the section_header_table
		self.sections = list()

		for i in range(self.header.e_shnum):
			'''
			uint32_t   sh_name;

			This member specifies the name of the section.  Its value is an
			index into the section header string table section,  giving the
			location of a null-terminated string.


			uint32_t   sh_type;

			This member categorizes the section's contents and semantics.


			uintN_t    sh_flags;        (N = 32/64)

			Sections support one-bit flags that describe miscellaneous
			attributes.  If a flag bit is set in sh_flags,  the  attribute
			is "on" for the section.  Otherwise, the attribute is "off" or
			does not apply.  Undefined attributes are set to zero.


			ElfN_Addr  sh_addr;         (N = 32/64)

			If this section appears in the memory image of a process, this
			member holds the address at which the section's first byte
			should reside.  Otherwise, the member contains zero.


			ElfN_Off  sh_offset;        (N = 32/64)

			This  member's  value holds the byte offset from the beginning
			of the file to the first byte in the section.  One section
			type, SHT_NOBITS, occupies no space in the file, and its
			sh_offset member locates the conceptual placement in the file.


			uintN_t    sh_size;         (N = 32/64)

			This member holds the section's size in bytes.  Unless the section
			type is SHT_NOBITS, the section occupies sh_size bytes
			in the file.  A section of type SHT_NOBITS may have a nonzero
			size, but it occupies no space in the file.


			uint32_t   sh_link;

			This member holds a section header table index link, whose
			interpretation depends on the section type.


			uint32_t   sh_info;

			This member holds extra information, whose interpretation
			depends on the section type.


			uintN_t    sh_addralign;    (N = 32/64)

			Some  sections  have  address  alignment constraints.  If a
			section holds a doubleword, the system must ensure doubleword
			alignment for the entire section.  That is, the value of  sh_addr
			must  be  congruent  to  zero,  modulo  the  value  of
			sh_addralign.   Only zero and positive integral powers of two
			are allowed.  Values of zero or one mean the section has no
			alignment constraints.


			uintN_t    sh_entsize;      (N = 32/64)

			Some sections hold a table of fixed-sized entries, such as a
			symbol table.  For such a section,  this  member  gives  the
			size in bytes for each entry.  This member contains zero if
			the section does not hold a table of fixed-size entries.
			'''

			tempSectionEntry = ElfN_Shdr()
			tempOffset = self.header.e_shoff + i*self.header.e_shentsize

			if self.bits == 32:
				fmt = '< 2I 4I 2I 2I'
			elif self.bits == 64:
				fmt = '< 2I 4Q 2I 2Q'

			fmtSize = struct.calcsize(fmt)
			assert fmtSize == self.header.e_shentsize

			(
					tempSectionEntry.sh_name,
					tempSectionEntry.sh_type,
					tempSectionEntry.sh_flags,      # 32/64 bit!
					tempSectionEntry.sh_addr,       # 32/64 bit!
					tempSectionEntry.sh_offset,     # 32/64 bit!
					tempSectionEntry.sh_size,       # 32/64 bit!
					tempSectionEntry.sh_link,
					tempSectionEntry.sh_info,
					tempSectionEntry.sh_addralign,  # 32/64 bit!
					tempSectionEntry.sh_entsize,    # 32/64 bit!
			) = struct.unpack(fmt, buffer_list[tempOffset:tempOffset+fmtSize])
			del tempOffset
			del fmtSize

			# create new section and add to sections list
			section = Section()
			section.elfN_shdr = tempSectionEntry
			self.sections.append(section)


		###############################################
		# parse section string table

		# section string table first byte always 0 byte
		# section string table last byte always 0 byte
		# section string table holds null terminated strings
		# empty section string table => sh_size of string table section = 0
		# => Non-zero indexes to string table are invalid

		# list of sections not empty => read whole string table
		if self.sections:
			nStart = self.sections[self.header.e_shstrndx].elfN_shdr.sh_offset
			nEnd = nStart + self.sections[self.header.e_shstrndx].elfN_shdr.sh_size
			stringtable_str = buffer_list[nStart:nEnd]

			# get name from string table for each section
			for i in range(len(self.sections)):

				# check if string table exists => abort reading
				if len(stringtable_str) == 0:
					break

				nStart = self.sections[i].elfN_shdr.sh_name
				nEnd = stringtable_str.find('\x00', nStart)
				# use empty string if string is not terminated (nEnd == -1)
				nEnd = max(nStart, nEnd)
				self.sections[i].sectionName = bytes(stringtable_str[nStart:nEnd])


		###############################################
		# parse program header table

		'''
		typedef struct {
			uint32_t   p_type;
			Elf32_Off  p_offset;
			Elf32_Addr p_vaddr;
			Elf32_Addr p_paddr;
			uint32_t   p_filesz;
			uint32_t   p_memsz;
			uint32_t   p_flags;
			uint32_t   p_align;
		} Elf32_Phdr;

		typedef struct {
			uint32_t   p_type;
			uint32_t   p_flags;
			Elf64_Off  p_offset;
			Elf64_Addr p_vaddr;
			Elf64_Addr p_paddr;
			uint64_t   p_filesz;
			uint64_t   p_memsz;
			uint64_t   p_align;
		} Elf64_Phdr;

		The main difference lies in the location of p_flags within the struct.
		'''

		# create a list of the program_header_table
		self.segments = list()

		for i in range(self.header.e_phnum):
			'''
			uint32_t   p_type;

			This  member  of  the Phdr struct tells what kind of segment
			this array element describes or how to interpret the array
			element's information.


			(uint32_t  p_flags;         (Elf64_Phdr only, see below))


			ElfN_Off   p_offset;        (N = 32/64)

			This member holds the offset from the beginning of the
			file at which the first byte of the segment resides.


			ElfN_Addr  p_vaddr;         (N = 32/64)

			This member holds the virtual address at which the first
			byte of the segment resides in memory.


			ElfN_Addr  p_paddr;         (N = 32/64)

			On  systems  for  which  physical  addressing  is relevant, this
			member is reserved for the segment's physical address.
			Under BSD this member is not used and must be zero.


			uintN_t    p_filesz;        (N = 32/64)

			This member holds the number of bytes in the file image of
			the segment.  It may be zero.


			uintN_t    p_memsz;         (N = 32/64)

			This member holds the number of bytes in the memory image
			of the segment.  It may be zero.


			uint32_t   p_flags;         (Elf32_Phdr only, for 64 see above)

			This member holds a bitmask of flags relevant to the segment:

			PF_X   An executable segment.
			PF_W   A writable segment.
			PF_R   A readable segment.

			A text segment commonly has the flags PF_X and PF_R.
			A data segment commonly has PF_X, PF_W and PF_R.

			uintN_t    p_align;         (N = 32/64)

			This member holds the value to which the segments are aligned
			in memory and in the  file.   Loadable  process  segments
			must have congruent values for p_vaddr and p_offset, modulo
			the page size.  Values of zero and one mean no alignment is
			required.  Otherwise, p_align should be a positive, integral
			power of two, and p_vaddr should  equal  p_offset,  modulo
			p_align.
			'''

			tempSegment = Segment()
			tempOffset = self.header.e_phoff + i*self.header.e_phentsize

			if self.bits == 32:
				unpackedSegment = struct.unpack('< I 5I I I', \
						buffer_list[tempOffset:tempOffset+32])
			elif self.bits == 64:
				unpackedSegment = struct.unpack('< I I 5Q Q', \
						buffer_list[tempOffset:tempOffset+56])
				# order elements as in Elf32_Phdr
				unpackedSegment = unpackedSegment[0:1] + unpackedSegment[2:7] \
						+ unpackedSegment[1:2] + unpackedSegment[7:8]

			del tempOffset

			(
					tempSegment.elfN_Phdr.p_type,
					tempSegment.elfN_Phdr.p_offset, # 32/64 bit!
					tempSegment.elfN_Phdr.p_vaddr,  # 32/64 bit!
					tempSegment.elfN_Phdr.p_paddr,  # 32/64 bit!
					tempSegment.elfN_Phdr.p_filesz, # 32/64 bit!
					tempSegment.elfN_Phdr.p_memsz,  # 32/64 bit!
					tempSegment.elfN_Phdr.p_flags,  # position as in Elf32_Phdr
					tempSegment.elfN_Phdr.p_align,  # 32/64 bit!
			) = unpackedSegment

			# check which sections are in the current segment
			# (in memory) and add them
			for section in self.sections:
				segStart = tempSegment.elfN_Phdr.p_vaddr
				segEnd = segStart + tempSegment.elfN_Phdr.p_memsz
				sectionStart = section.elfN_shdr.sh_addr
				sectionEnd = sectionStart + section.elfN_shdr.sh_size

				if segStart <= sectionStart and sectionEnd <= segEnd:
					tempSegment.sectionsWithin.append(section)

			self.segments.append(tempSegment)


		# get all segments within a segment
		for outerSegment in self.segments:
			# PT_GNU_STACK only holds access rights
			if outerSegment.elfN_Phdr.p_type == P_type.PT_GNU_STACK:
				continue

			for segmentWithin in self.segments:
				# PT_GNU_STACK only holds access rights
				if segmentWithin.elfN_Phdr.p_type == P_type.PT_GNU_STACK:
					continue

				if segmentWithin == outerSegment:
					continue

				innerStart = segmentWithin.elfN_Phdr.p_offset
				innerEnd = innerStart + segmentWithin.elfN_Phdr.p_filesz
				outerStart = outerSegment.elfN_Phdr.p_offset
				outerEnd = outerStart + outerSegment.elfN_Phdr.p_filesz

				if outerStart <= innerStart and innerEnd <= outerEnd:
					outerSegment.segmentsWithin.append(segmentWithin)


		###############################################
		# parse dynamic segment entries

		'''
		typedef struct {
			Elf32_Sword    d_tag;
			union {
				Elf32_Word d_val;
				Elf32_Addr d_ptr;
			} d_un;
		} Elf32_Dyn;

		typedef struct {
			Elf64_Sxword    d_tag;
			union {
				Elf64_Xword d_val;
				Elf64_Addr  d_ptr;
			} d_un;
		} Elf64_Dyn;
		'''

		# find dynamic segment
		dynamicSegment = None
		for segment in self.segments:
			if segment.elfN_Phdr.p_type == P_type.PT_DYNAMIC:
				dynamicSegment = segment
				break
		if dynamicSegment is None:
			raise ValueError("Segment of type PT_DYNAMIC was not found.")

		# create a list for all dynamic segment entries
		self.dynamicSegmentEntries = list()

		if self.bits == 32:
			structFmt = '<II'
		elif self.bits == 64:
			structFmt = '<QQ'

		dynSegEntrySize = struct.calcsize(structFmt)

		endReached = False
		for i in range((dynamicSegment.elfN_Phdr.p_filesz / dynSegEntrySize)):

			# parse dynamic segment entry
			dynSegmentEntry = ElfN_Dyn()

			tempOffset = dynamicSegment.elfN_Phdr.p_offset + i*dynSegEntrySize
			(
					dynSegmentEntry.d_tag,
					dynSegmentEntry.d_un,
			) = struct.unpack(structFmt,
					self.data[tempOffset:tempOffset+dynSegEntrySize])

			del tempOffset

			# add dynamic segment entry to list
			self.dynamicSegmentEntries.append(dynSegmentEntry)

			# check if the end of the dynamic segment array is reached
			if dynSegmentEntry.d_tag == D_tag.DT_NULL:
				endReached = True
				break

		# check if end was reached with PT_NULL entry
		if not endReached:
			raise ValueError("PT_NULL was not found in segment of type" \
			+ "PT_DYNAMIC (malformed ELF executable/shared object).")


		###############################################
		# parse relocation entries


		# search for relocation entries in dynamic segment entries
		jmpRelOffset = None
		pltRelSize = None
		pltRelType = None
		relEntrySize = None
		relOffset = None
		relSize = None
		relaEntrySize = None
		relaOffset = None
		relaSize = None
		symbolEntrySize = None
		symbolTableOffset = None
		stringTableOffset = None
		stringTableSize = None
		for dynEntry in self.dynamicSegmentEntries:
			if dynEntry.d_tag == D_tag.DT_JMPREL:
				if jmpRelOffset is not None:
					raise ValueError("Can't handle multiple DT_JMPREL")
				jmpRelOffset = self.virtualMemoryAddrToFileOffset(dynEntry.d_un)
				continue
			if dynEntry.d_tag == D_tag.DT_PLTRELSZ:
				pltRelSize = dynEntry.d_un
				continue
			if dynEntry.d_tag == D_tag.DT_PLTREL:
				pltRelType = dynEntry.d_un
				continue
			if dynEntry.d_tag == D_tag.DT_RELENT:
				if relEntrySize is not None:
					raise ValueError("Can't handle multiple DT_RELENT")
				relEntrySize = dynEntry.d_un
				continue
			if dynEntry.d_tag == D_tag.DT_RELAENT:
				if relaEntrySize is not None:
					raise ValueError("Can't handle multiple DT_RELAENT")
				relaEntrySize = dynEntry.d_un
				continue
			if dynEntry.d_tag == D_tag.DT_REL:
				if relOffset is not None:
					raise ValueError("Can't handle multiple DT_REL")
				relOffset = self.virtualMemoryAddrToFileOffset(dynEntry.d_un)
				continue
			if dynEntry.d_tag == D_tag.DT_RELA:
				if relaOffset is not None:
					raise ValueError("Can't handle multiple DT_RELA")
				relaOffset = self.virtualMemoryAddrToFileOffset(dynEntry.d_un)
				continue
			if dynEntry.d_tag == D_tag.DT_RELSZ:
				relSize = dynEntry.d_un
				continue
			if dynEntry.d_tag == D_tag.DT_RELASZ:
				relaSize = dynEntry.d_un
				continue
			if dynEntry.d_tag == D_tag.DT_SYMENT:
				symbolEntrySize = dynEntry.d_un
				continue
			if dynEntry.d_tag == D_tag.DT_SYMTAB:
				# get the offset in the file of the symbol table
				symbolTableOffset = self.virtualMemoryAddrToFileOffset(
					dynEntry.d_un)
				continue
			if dynEntry.d_tag == D_tag.DT_STRTAB:
				# get the offset in the file of the string table
				stringTableOffset = self.virtualMemoryAddrToFileOffset(
					dynEntry.d_un)
				continue
			if dynEntry.d_tag == D_tag.DT_STRSZ:
				stringTableSize = dynEntry.d_un


		# check if ELF got needed entries
		if (stringTableOffset is None
			or stringTableSize is None
			or symbolTableOffset is None
			or symbolEntrySize is None):
			raise ValueError("No dynamic section entry of type DT_STRTAB," \
				" DT_STRSZ, DT_SYMTAB and/or DT_SYMENT found (malformed ELF" \
				" executable/shared object).")


		# estimate symbol table size in order to not rely on sections
		# when ELF is compiled with gcc, the .dynstr section (string table)
		# follows directly the .dynsym section (symbol table)
		# => size of symbol table is difference between string and symbol table
		estimatedSymbolTableSize = stringTableOffset - symbolTableOffset

		# find .dynsym section in sections
		# and only use if it exists once
		dynSymSection = None
		dynSymSectionDuplicated = False
		dynSymSectionIgnore = False
		dynSymEstimationIgnore = False
		for section in self.sections:
			if section.sectionName == ".dynsym":
				# check if .dynsym section only exists once
				# (because section entries are optional and can
				# be easily manipulated)
				if dynSymSection is None:
					dynSymSection = section

				# when .dynsym section exists multiple times
				# do not use it
				else:
					dynSymSectionDuplicated = True
					break

		# check if .dynsym section exists
		if dynSymSection is None:
			print 'NOTE: ".dynsym" section was not found. Trying to use ' \
				+ 'estimation to parse all symbols from the symbol table'
			dynSymSectionIgnore = True

		# check if .dynsym section was found multiple times
		elif dynSymSectionDuplicated is True:
			print 'NOTE: ".dynsym" section was found multiple times. ' \
				+ 'Trying to use estimation to parse all symbols from' \
				+ 'the symbol table'
			dynSymSectionIgnore = True

		# check if symbol table offset matches the offset of the
		# ".dynsym" section
		elif dynSymSection.elfN_shdr.sh_offset != symbolTableOffset:
			print 'NOTE: ".dynsym" section offset does not match ' \
				+ 'offset of symbol table. Ignoring the section ' \
				+ 'and using the estimation.'
			dynSymSectionIgnore = True

		# check if the size of the ".dynsym" section matches the
		# estimated size
		elif dynSymSection.elfN_shdr.sh_size != estimatedSymbolTableSize:

			# check if forceDynSymParsing was not set (default value is 0)
			if self.forceDynSymParsing == 0:
				print 'WARNING: ".dynsym" size does not match the estimated ' \
					+ 'size. One (or both) are wrong. Ignoring the dynamic ' \
					+ ' symbols. You can force the using of the ".dynsym" ' \
					+ 'section by setting "forceDynSymParsing=1" or force ' \
					+ 'the using of the estimated size by setting ' \
					+ '"forceDynSymParsing=2".'

				# ignore dynamic symbols
				dynSymSectionIgnore = True
				dynSymEstimationIgnore = True

			# forcing the use of the ".dynsym" section
			elif self.forceDynSymParsing == 1:

				dynSymSectionIgnore = False
				dynSymEstimationIgnore = True

			# forcing the use of the estimation
			elif self.forceDynSymParsing == 2:

				dynSymSectionIgnore = True
				dynSymEstimationIgnore = False

			# value does not exists
			else:
				raise TypeError('"forceDynSymParsing" uses an invalid value.')

		# use ".dynsym" section information (when considered correct)
		if dynSymSectionIgnore is False:

			# parse the complete symbol table based on the
			# ".dynsym" section
			for i in range(dynSymSection.elfN_shdr.sh_size \
				/ symbolEntrySize):

				tempOffset = symbolTableOffset + (i*symbolEntrySize)
				tempSymbol = self._parseDynamicSymbol(tempOffset,
					stringTableOffset, stringTableSize)

				# add entry to dynamic symbol entries list
				self.dynamicSymbolEntries.append(tempSymbol)

		# use estimation to parse dynamic symbols
		elif (dynSymSectionIgnore is True
			and dynSymEstimationIgnore is False):

			# parse the complete symbol table based on the
			# estimation
			for i in range(estimatedSymbolTableSize \
				/ symbolEntrySize):

				tempOffset = symbolTableOffset + (i*symbolEntrySize)
				tempSymbol = self._parseDynamicSymbol(tempOffset,
					stringTableOffset, stringTableSize)

				# add entry to dynamic symbol entries list
				self.dynamicSymbolEntries.append(tempSymbol)

		# holds tuples: (type, offset, size, targetlist)
		relocTODO = []

		# DT_JMPREL
		if jmpRelOffset is not None:
			if pltRelType is None:
				raise ValueError('DT_JMPREL present but DT_PLTREL not.')
			if pltRelSize is None:
				raise ValueError('DT_JMPREL present but DT_PLTRELSZ not.')

			if pltRelType == D_tag.DT_REL:
				if relEntrySize is None:
					raise ValueError('DT_JMPREL present with ' \
							+ ' DT_PLTREL == DT_REL, but DT_RELSZ not present')
			elif pltRelType == D_tag.DT_RELA:
				if relaEntrySize is None:
					raise ValueError('DT_JMPREL present with ' \
							+ ' DT_PLTREL == DT_RELA, but DT_RELASZ not present')
			else:
				raise ValueError('Invalid/unexpected DT_PLTREL (pltRelType).')

			self.jumpRelocationEntries = list()
			relocTODO.append((pltRelType, jmpRelOffset, pltRelSize,
				self.jumpRelocationEntries))

		# DT_REL (only mandatory hwn DT_RELA is not present)
		if relOffset is not None:
			if relSize is None:
				raise ValueError('DT_REL present but DT_RELSZ not.')

			if relEntrySize is None:
				raise ValueError('DT_REL present but DT_RELENT not.')

			self.relocationEntries = list()
			relocTODO.append((D_tag.DT_REL, relOffset, relSize,
				self.relocationEntries))

		# DT_RELA
		if relaOffset is not None:
			if relaSize is None:
				raise ValueError('DT_RELA present but DT_RELASZ not.')

			if relaEntrySize is None:
				raise ValueError('DT_RELA present but DT_RELAENT not.')

			self.relocationEntries = list()
			relocTODO.append((D_tag.DT_RELA, relaOffset, relaSize,
				self.relocationEntries))

		if relOffset is not None and relaOffset is not None:
			raise RuntimeError('INTERNAL ERROR: TODO REL READ 1')

		if len(relocTODO) < 1:
			raise RuntimeError('INTERNAL ERROR: TODO REL READ 2')


		for relocType, relocOffset, relocSize, relocList in relocTODO:
			if relocType == D_tag.DT_REL:
				relocEntrySize = relEntrySize
			elif relocType == D_tag.DT_RELA:
				relocEntrySize = relaEntrySize

			if relocType == D_tag.DT_REL:
				if self.bits == 32:
					structFmt = '<II'
				elif self.bits == 64:
					structFmt = '<QQ'
			elif relocType == D_tag.DT_RELA:
				if self.bits == 32:
					structFmt = '<IIi'
				elif self.bits == 64:
					structFmt = '<QQq'

			assert struct.calcsize(structFmt) == relocEntrySize

			for i in range(relocSize / relocEntrySize):
				tempOffset = relocOffset + i*relocEntrySize

				if relocType == D_tag.DT_REL:
					relocEntry = ElfN_Rel()
					(
						# ElfN_Addr     r_offset;    (N = 32/64)
						# in executable and share object files
						# => r_offset holds a virtual address
						relocEntry.r_offset,

						# ElfN_Word     r_info;      (N = 32/64)
						relocEntry.r_info,
					) = struct.unpack(structFmt, self.data[tempOffset:tempOffset+relocEntrySize])
				elif relocType == D_tag.DT_RELA:
					relocEntry = ElfN_Rela()
					(
						# ElfN_Addr     r_offset;    (N = 32/64)
						# in executable and share object files
						# => r_offset holds a virtual address
						relocEntry.r_offset,

						# ElfN_Word     r_info;      (N = 32/64)
						relocEntry.r_info,

						relocEntry.r_addend,
					) = struct.unpack(structFmt, self.data[tempOffset:tempOffset+relocEntrySize])

				del tempOffset

				(relocEntry.r_sym, relocEntry.r_type) = \
						self.relocationSymIdxAndTypeFromInfo(relocEntry.r_info)

				# get values from the symbol table
				tempOffset = symbolTableOffset \
					+ (relocEntry.r_sym*symbolEntrySize)
				tempSymbol = self._parseDynamicSymbol(tempOffset,
					stringTableOffset, stringTableSize)

				# check if parsed dynamic symbol already exists
				# if it does => use already existed dynamic symbol
				# else => use newly parsed dynamic symbol
				dynamicSymbolFound = False
				for dynamicSymbol in self.dynamicSymbolEntries:
					if (tempSymbol.ElfN_Sym.st_name
						== dynamicSymbol.ElfN_Sym.st_name
						and tempSymbol.ElfN_Sym.st_value
						== dynamicSymbol.ElfN_Sym.st_value
						and tempSymbol.ElfN_Sym.st_size
						== dynamicSymbol.ElfN_Sym.st_size
						and tempSymbol.ElfN_Sym.st_info
						== dynamicSymbol.ElfN_Sym.st_info
						and tempSymbol.ElfN_Sym.st_other
						== dynamicSymbol.ElfN_Sym.st_other
						and tempSymbol.ElfN_Sym.st_shndx
						== dynamicSymbol.ElfN_Sym.st_shndx):
						relocEntry.symbol = dynamicSymbol
						dynamicSymbolFound = True
						break
				if dynamicSymbolFound is False:
					relocEntry.symbol = tempSymbol

				relocList.append(relocEntry)


	# this function dumps a list of relocations (used in printElf())
	# return values: None
	def printRelocations(self, relocationList, title):
		printAddend = len(relocationList) \
				and type(relocationList[0]) == ElfN_Rela

		# output all jump relocation entries
		print("%s (%d entries)" % (title, len(relocationList)))
		print("No."),
		print("\t"),
		print("MemAddr"),
		print("\t"),
		print("File offset"),
		print("\t"),
		print("Info"),
		print("\t\t"),
		print("Type"),
		print("\t\t"),
		if printAddend:
			print("Addend"),
			print("\t\t"),
		print("Sym. value"),
		print("\t"),
		print("Sym. name"),
		print
		print("\t"),
		print("(r_offset)"),
		print("\t"),
		print("\t"),
		print("\t"),
		print("(r_info)"),
		print("\t"),
		print("(r_type)"),
		if printAddend:
			print("\t"),
			print("(r_addend)"),
		print

		counter = 0
		for entry in relocationList:
			symbol = entry.symbol.ElfN_Sym
			print("%d" % counter),
			print("\t"),
			print("0x" + ("%x" % entry.r_offset).zfill(8)),
			print("\t"),

			# try to convert the virtual memory address to a file offset
			# in executable and share object files
			# => r_offset holds a virtual address
			try:
				print("0x" + ("%x" \
					% self.virtualMemoryAddrToFileOffset(
					entry.r_offset)).zfill(8)),
			except:
				print("None\t"),

			print("\t"),
			print("0x" + ("%x" % entry.r_info).zfill(8)),
			print("\t"),

			# translate type
			if entry.r_type in R_type.reverse_lookup.keys():
				print("%s" % R_type.reverse_lookup[entry.r_type]),
			else:
				print("0x%x" % entry.r_type),

			if printAddend:
				if type(entry) == ElfN_Rela:
					print("\t"),
					print("0x" + ("%x" % entry.r_addend).zfill(8)),
				else:
					print("\t\t"),

			print("\t"),
			print("0x" + ("%x" % symbol.st_value).zfill(8)),

			print("\t"),
			print(entry.symbol.symbolName),

			print

			counter += 1

		print


	# this function outputs the parsed ELF file (like readelf)
	# return values: None
	def printElf(self):

		# check if the file was completely parsed before
		if self.fileParsed is False:
			raise ValueError("Operation not possible. " \
				+ "File was not completely parsed before.")

		# output header
		print "ELF header:"
		print "Type: %s" % ElfN_Ehdr.E_type.reverse_lookup[self.header.e_type]
		print "Version: %s" \
			% ElfN_Ehdr.EI_VERSION.reverse_lookup[self.header.e_ident[6]]
		print "Machine: %s" \
			% ElfN_Ehdr.E_machine.reverse_lookup[self.header.e_machine]
		print "Entry point address: 0x%x" % self.header.e_entry
		print "Program header table offset in bytes: 0x%x (%d)" \
			% (self.header.e_phoff, self.header.e_phoff)
		print "Section header table offset in bytes: 0x%x (%d)" \
			% (self.header.e_shoff, self.header.e_shoff)
		print "Flags: 0x%x (%d)" % (self.header.e_flags, self.header.e_flags)
		print "Size of ELF header in bytes: 0x%x (%d)" \
			% (self.header.e_ehsize, self.header.e_ehsize)
		print "Size of each program header entry in bytes: 0x%x (%d)" \
			% (self.header.e_phentsize, self.header.e_phentsize)
		print "Number of program header entries: %d" % self.header.e_phnum
		print "Size of each sections header entry in bytes: 0x%x (%d)" \
			% (self.header.e_shentsize, self.header.e_shentsize)
		print "Number of section header entries: %d" % self.header.e_shnum
		print "Section header string table index: %d" % self.header.e_shstrndx
		print


		# output of all sections
		counter = 0
		for section in self.sections:
			print "Section No. %d" % counter
			print "Name: %s" % section.sectionName

			# translate type
			if section.elfN_shdr.sh_type in SH_type.reverse_lookup.keys():
				print "Type: %s" \
					% SH_type.reverse_lookup[section.elfN_shdr.sh_type]
			else:
				print "Unknown Type: 0x%x (%d)" \
					% (section.elfN_shdr.sh_type, section.elfN_shdr.sh_type)

			print "Addr: 0x%x" % section.elfN_shdr.sh_addr
			print "Off: 0x%x" % section.elfN_shdr.sh_offset
			print "Size: 0x%x (%d)" \
				% (section.elfN_shdr.sh_size, section.elfN_shdr.sh_size)
			print "ES: %d" % section.elfN_shdr.sh_entsize

			# translate flags
			temp = ""
			if (section.elfN_shdr.sh_flags & SH_flags.SHF_WRITE) != 0:
				temp += "W"
			if (section.elfN_shdr.sh_flags & SH_flags.SHF_ALLOC) != 0:
				temp += "A"
			if (section.elfN_shdr.sh_flags & SH_flags.SHF_EXECINSTR) != 0:
				temp += "X"

			print "FLG: %s" % temp
			print "Lk: %d" % section.elfN_shdr.sh_link
			print "Inf: %d" % section.elfN_shdr.sh_info
			print "Al: %d" % section.elfN_shdr.sh_addralign
			print
			counter += 1


		# output of all segments
		counter = 0
		for segment in self.segments:
			print "Segment No. %d" % counter

			# translate type
			if segment.elfN_Phdr.p_type in P_type.reverse_lookup.keys():
				print "Type: %s" \
					% P_type.reverse_lookup[segment.elfN_Phdr.p_type]
			else:
				print "Unknown Type: 0x%x (%d)" \
					% (segment.elfN_Phdr.p_type, segment.elfN_Phdr.p_type)

			print "Offset: 0x%x" % segment.elfN_Phdr.p_offset
			print "Virtual Addr: 0x%x" % segment.elfN_Phdr.p_vaddr
			print "Physical Addr: 0x%x" % segment.elfN_Phdr.p_paddr
			print "File Size: 0x%x (%d)" \
				% (segment.elfN_Phdr.p_filesz, segment.elfN_Phdr.p_filesz)
			print "Mem Size: 0x%x (%d)" \
				% (segment.elfN_Phdr.p_memsz, segment.elfN_Phdr.p_memsz)

			# translate flags
			temp = ""
			if (segment.elfN_Phdr.p_flags & P_flags.PF_R) != 0:
				temp += "R"
			if (segment.elfN_Phdr.p_flags & P_flags.PF_W) != 0:
				temp += "W"
			if (segment.elfN_Phdr.p_flags & P_flags.PF_X) != 0:
				temp += "X"
			print "Flags: %s" % temp

			print "Align: 0x%x" % segment.elfN_Phdr.p_align

			# print which sections are in the current segment (in memory)
			temp = ""
			for section in segment.sectionsWithin:
					temp += section.sectionName + " "
			if temp != "":
				print "Sections in segment: " + temp

			# print which segments are within current segment (in file)
			temp = ""
			for segmentWithin in segment.segmentsWithin:
				for i in range(len(self.segments)):
					if segmentWithin == self.segments[i]:
						temp += "%d, " % i
						break
			if temp != "":
				print "Segments within segment: " + temp

			# get interpreter if segment is for interpreter
			# null-terminated string
			if segment.elfN_Phdr.p_type == P_type.PT_INTERP:
				nStart = segment.elfN_Phdr.p_offset
				nEnd = nStart + segment.elfN_Phdr.p_filesz
				print "Interpreter: %s" % self.data[nStart:nEnd]

			print
			counter += 1


		# search string table entry, string table size,
		# symbol table entry and symbol table entry size
		stringTableOffset = None
		stringTableSize = None
		symbolTableOffset = None
		symbolEntrySize = None
		for searchEntry in self.dynamicSegmentEntries:
			if searchEntry.d_tag == D_tag.DT_STRTAB:
				# data contains virtual memory address
				# => calculate offset in file
				stringTableOffset = \
					self.virtualMemoryAddrToFileOffset(searchEntry.d_un)
			if searchEntry.d_tag == D_tag.DT_STRSZ:
				stringTableSize = searchEntry.d_un
			if searchEntry.d_tag == D_tag.DT_SYMTAB:
				# data contains virtual memory address
				# => calculate offset in file
				symbolTableOffset = \
					self.virtualMemoryAddrToFileOffset(searchEntry.d_un)
			if searchEntry.d_tag == D_tag.DT_SYMENT:
				symbolEntrySize = searchEntry.d_un

		if (stringTableOffset is None
			or stringTableSize is None
			or symbolTableOffset is None
			or symbolEntrySize is None):
			raise ValueError("No dynamic section entry of type DT_STRTAB," \
				+ " DT_STRSZ, DT_SYMTAB and/or DT_SYMENT found (malformed"\
				+ " ELF executable/shared object).")


		# output all dynamic segment entries
		counter = 0
		for entry in self.dynamicSegmentEntries:
			print "Dynamic segment entry No. %d" % counter
			if entry.d_tag in D_tag.reverse_lookup.keys():
				print "Type: %s" % D_tag.reverse_lookup[entry.d_tag]
			else:
				print "Unknwon Type: 0x%x (%d)" % (entry.d_tag, entry.d_tag)

			# check if entry tag equals DT_NEEDED => get library name
			if entry.d_tag == D_tag.DT_NEEDED:
				nStart = stringTableOffset + entry.d_un
				nMaxEnd = stringTableOffset + stringTableSize
				nEnd = self.data.find('\x00', nStart, nMaxEnd)
				nEnd = max(nStart, nEnd)
				temp = bytes(self.data[nStart:nEnd])
				print "Name/Value: 0x%x (%d) (%s)" \
					% (entry.d_un, entry.d_un, temp)
			else:
				print "Name/Value: 0x%x (%d)" % (entry.d_un, entry.d_un)

			print
			counter += 1

		self.printRelocations(self.jumpRelocationEntries,
				"Jump relocation entries")

		self.printRelocations(self.relocationEntries,
				"Relocation entries")

		# output all dynamic symbol entries
		print("Dynamic symbols (%d entries)" % len(self.dynamicSymbolEntries))
		print("No."),
		print("\t"),
		print("Value"),
		print("\t\t"),
		print("Size"),
		print("\t"),
		print("Name"),
		print

		counter = 0
		for entry in self.dynamicSymbolEntries:
			symbol = entry.ElfN_Sym
			print("%d" % counter),
			print("\t"),
			print("0x" + ("%x" % symbol.st_value).zfill(8)),
			print("\t"),
			print("0x" + ("%x" % symbol.st_size).zfill(3)),
			print("\t"),
			print("%s" % entry.symbolName),

			print
			counter += 1


	# this function generates a new ELF file from the attributes of the object
	# return values: (list) generated ELF file data
	def generateElf(self):

		# check if the file was completely parsed before
		if self.fileParsed is False:
			raise ValueError("Operation not possible. " \
				+ "File was not completely parsed before.")

		# copy binary data to new list
		newfile = self.data[:]

		# ------

		# get position of section header table
		writePosition = self.header.e_shoff

		# fill list with null until writePosition is reached
		if len(newfile) < writePosition:
			newfile.extend(bytearray(writePosition - len(newfile)))

		# write section header table back
		for section in self.sections:
			temp = self.sectionHeaderEntryToBytearray(section.elfN_shdr)
			newfile[writePosition:writePosition+len(temp)] = temp
			writePosition += len(temp)

		# ------

		# when defined => write string table back
		if self.header.e_shstrndx != Shstrndx.SHN_UNDEF:
			for section in self.sections:
				# calculate the position on which the name should be written
				writePosition = \
					self.sections[self.header.e_shstrndx].elfN_shdr.sh_offset \
					+ section.elfN_shdr.sh_name

				# fill list with null until writePosition is reached
				if len(newfile) < writePosition:
					newfile.extend(bytearray(writePosition - len(newfile)))

				# write name of all sections into string table
				data = bytearray(section.sectionName) + b'\x00'
				newfile[writePosition:writePosition+len(data)] = data
				writePosition += len(data)

		# ------

		# write ELF header back
		newfile[0:len(self.header.e_ident)] = self.header.e_ident

		headerFields = (
			# uint16_t      e_type;
			self.header.e_type,
			# uint16_t      e_machine;
			self.header.e_machine,
			# uint32_t      e_version;
			self.header.e_version,
			# ElfN_Addr     e_entry;   (32/64 bit)
			self.header.e_entry,
			# ElfN_Off      e_phoff;   (32/64 bit)
			self.header.e_phoff,
			# ElfN_Off      e_shoff;   (32/64 bit)
			self.header.e_shoff,
			# uint32_t      e_flags;
			self.header.e_flags,
			# uint16_t      e_ehsize;
			self.header.e_ehsize,
			# uint16_t      e_phentsize;
			self.header.e_phentsize,
			# uint16_t      e_phnum;
			self.header.e_phnum,
			# uint16_t      e_shentsize;
			self.header.e_shentsize,
			# uint16_t      e_shnum;
			self.header.e_shnum,
			# uint16_t      e_shstrndx;
			self.header.e_shstrndx
		)

		if self.bits == 32:
			newfile[16:52] = struct.pack('< 2H I 3I I 6H', *headerFields)
		elif self.bits == 64:
			newfile[16:64] = struct.pack('< 2H I 3Q I 6H', *headerFields)

		# ------

		# write programm header table back
		for i in range(len(self.segments)):

			# add placeholder bytes to new file when the bytes do not already
			# exist in the new file until size of header entry fits
			requiredSize = self.header.e_phoff + ((i+1) * self.header.e_phentsize)
			if len(newfile) < requiredSize:
				newfile.extend(bytearray(requiredSize - len(newfile)))

			tempOffset = self.header.e_phoff + i*self.header.e_phentsize
			'''
			typedef struct {
				uint32_t   p_type;
				Elf32_Off  p_offset;
				Elf32_Addr p_vaddr;
				Elf32_Addr p_paddr;
				uint32_t   p_filesz;
				uint32_t   p_memsz;
				uint32_t   p_flags;   // *
				uint32_t   p_align;
			} Elf32_Phdr;

			typedef struct {
				uint32_t   p_type;
				uint32_t   p_flags;   // *
				Elf64_Off  p_offset;
				Elf64_Addr p_vaddr;
				Elf64_Addr p_paddr;
				uint64_t   p_filesz;
				uint64_t   p_memsz;
				uint64_t   p_align;
			} Elf64_Phdr;

			The main difference lies in the location of p_flags within the struct.
			'''
			if self.bits == 32:
				fmt = '< I 5I I I'
				fmtSize = struct.calcsize(fmt)
				assert self.header.e_phentsize == fmtSize
				newfile[tempOffset:tempOffset+fmtSize] = struct.pack(fmt,
					self.segments[i].elfN_Phdr.p_type,
					self.segments[i].elfN_Phdr.p_offset,
					self.segments[i].elfN_Phdr.p_vaddr,
					self.segments[i].elfN_Phdr.p_paddr,
					self.segments[i].elfN_Phdr.p_filesz,
					self.segments[i].elfN_Phdr.p_memsz,
					self.segments[i].elfN_Phdr.p_flags,     # <- p_flags
					self.segments[i].elfN_Phdr.p_align,
				)
			elif self.bits == 64:
				fmt = '< I I 5Q Q'
				fmtSize = struct.calcsize(fmt)
				assert self.header.e_phentsize == fmtSize
				newfile[tempOffset:tempOffset+fmtSize] = struct.pack(fmt,
					self.segments[i].elfN_Phdr.p_type,
					self.segments[i].elfN_Phdr.p_flags,     # <- p_flags
					self.segments[i].elfN_Phdr.p_offset,
					self.segments[i].elfN_Phdr.p_vaddr,
					self.segments[i].elfN_Phdr.p_paddr,
					self.segments[i].elfN_Phdr.p_filesz,
					self.segments[i].elfN_Phdr.p_memsz,
					self.segments[i].elfN_Phdr.p_align,
				)
			del tempOffset


		# ------

		# find dynamic segment
		dynamicSegment = None
		for segment in self.segments:
			if segment.elfN_Phdr.p_type == P_type.PT_DYNAMIC:
				dynamicSegment = segment
				break
		if dynamicSegment is None:
			raise ValueError("Segment of type PT_DYNAMIC was not found.")

		if self.bits == 32:
			structFmt = '<II'
		elif self.bits == 64:
			structFmt = '<QQ'

		dynSegEntrySize = struct.calcsize(structFmt)

		# write all dynamic segment entries back
		for i in range(len(self.dynamicSegmentEntries)):

			tempOffset = dynamicSegment.elfN_Phdr.p_offset + i*dynSegEntrySize
			newfile[tempOffset:tempOffset+dynSegEntrySize] = struct.pack(structFmt,
				# ElfN_Sword    d_tag;
				self.dynamicSegmentEntries[i].d_tag,

				# union {
				#       ElfN_Word d_val;
				#       ElfN_Addr d_ptr;
				# } d_un;
				self.dynamicSegmentEntries[i].d_un,
			)
			del tempOffset

		# overwrite rest of segment with 0x00 (default padding data)
		# (NOTE: works in all test cases, but can cause md5 parsing
		# check to fail!)
		tmpStart = dynamicSegment.elfN_Phdr.p_offset \
				+ len(self.dynamicSegmentEntries) * dynSegEntrySize
		tmpEnd = dynamicSegment.elfN_Phdr.p_offset \
				+ dynamicSegment.elfN_Phdr.p_filesz
		if tmpStart < tmpEnd:
			newfile[tmpStart:tmpEnd] = bytearray(tmpEnd - tmpStart)

		# ------

		# search for relocation entries in dynamic segment entries
		jmpRelOffset = None
		pltRelSize = None
		pltRelType = None
		relEntrySize = None
		relOffset = None
		relSize = None
		relaEntrySize = None
		relaOffset = None
		relaSize = None
		symbolTableOffset = None
		symbolEntrySize = None
		for dynEntry in self.dynamicSegmentEntries:
			if dynEntry.d_tag == D_tag.DT_JMPREL:
				if jmpRelOffset is not None:
					raise ValueError("Can't handle multiple DT_JMPREL")
				jmpRelOffset = self.virtualMemoryAddrToFileOffset(dynEntry.d_un)
				continue
			if dynEntry.d_tag == D_tag.DT_PLTRELSZ:
				pltRelSize = dynEntry.d_un
				continue
			if dynEntry.d_tag == D_tag.DT_PLTREL:
				pltRelType = dynEntry.d_un
				continue
			if dynEntry.d_tag == D_tag.DT_RELENT:
				if relEntrySize is not None:
					raise ValueError("Can't handle multiple DT_RELENT")
				relEntrySize = dynEntry.d_un
				continue
			if dynEntry.d_tag == D_tag.DT_RELAENT:
				if relaEntrySize is not None:
					raise ValueError("Can't handle multiple DT_RELAENT")
				relaEntrySize = dynEntry.d_un
				continue
			if dynEntry.d_tag == D_tag.DT_REL:
				if relOffset is not None:
					raise ValueError("Can't handle multiple DT_REL")
				relOffset = self.virtualMemoryAddrToFileOffset(dynEntry.d_un)
				continue
			if dynEntry.d_tag == D_tag.DT_RELA:
				if relaOffset is not None:
					raise ValueError("Can't handle multiple DT_RELA")
				relaOffset = self.virtualMemoryAddrToFileOffset(dynEntry.d_un)
				continue
			if dynEntry.d_tag == D_tag.DT_RELSZ:
				relSize = dynEntry.d_un
				continue
			if dynEntry.d_tag == D_tag.DT_RELASZ:
				relaSize = dynEntry.d_un
				continue
			if dynEntry.d_tag == D_tag.DT_SYMTAB:
				# get the offset in the file of the symbol table
				symbolTableOffset = self.virtualMemoryAddrToFileOffset(
					dynEntry.d_un)
				continue
			if dynEntry.d_tag == D_tag.DT_SYMENT:
				symbolEntrySize = dynEntry.d_un


		# write dynamic symbols back to dynamic symbol table
		# (if the dynamic symbol table could be parsed)
		for i in range(len(self.dynamicSymbolEntries)):
			if symbolTableOffset is not None:
				self._writeDynamicSymbol(newfile,
						symbolTableOffset + i * symbolEntrySize,
						self.dynamicSymbolEntries[i].ElfN_Sym)

		# for fast lookups
		dynSymSet = set(self.dynamicSymbolEntries)


		# => write (jump) relocation entries back

		# holds tuples: (type, offset, size, sourcelist)
		relocTODO = []

		# DT_JMPREL
		if jmpRelOffset is not None:
			relocTODO.append((pltRelType, jmpRelOffset, pltRelSize,
				self.jumpRelocationEntries))

		# DT_REL
		if relOffset is not None:
			relocTODO.append((D_tag.DT_REL, relOffset, relSize,
				self.relocationEntries))

		# DT_RELA
		if relaOffset is not None:
			relocTODO.append((D_tag.DT_RELA, relaOffset, relaSize,
				self.relocationEntries))

		if relOffset is not None and relaOffset is not None:
			raise RuntimeError('INTERNAL ERROR: TODO REL WRITE 1')


		for relocType, relocOffset, relocSize, relocList in relocTODO:
			if relocType == D_tag.DT_REL:
				relocEntrySize = relEntrySize
			elif relocType == D_tag.DT_RELA:
				relocEntrySize = relaEntrySize

			if relocType == D_tag.DT_REL:
				if self.bits == 32:
					structFmt = '<II'
				elif self.bits == 64:
					structFmt = '<QQ'
			elif relocType == D_tag.DT_RELA:
				if self.bits == 32:
					structFmt = '<IIi'
				elif self.bits == 64:
					structFmt = '<QQq'

			assert struct.calcsize(structFmt) == relocEntrySize

			for i, relocEntry in enumerate(relocList):
				tempOffset = relocOffset + (i*relocEntrySize)

				if relocType == D_tag.DT_REL:
					newfile[tempOffset:tempOffset+relocEntrySize] = struct.pack(
							structFmt,
							relocEntry.r_offset,
							relocEntry.r_info,
					)
				elif relocType == D_tag.DT_RELA:
					newfile[tempOffset:tempOffset+relocEntrySize] = struct.pack(
							structFmt,
							relocEntry.r_offset,
							relocEntry.r_info,
							relocEntry.r_addend,
					)

				del tempOffset

				# check if dynamic symbol was already written
				# when writing all dynamic symbol entries back
				# if not => write dynamic symbol back
				dynSym = relocEntry.symbol
				if (dynSym not in dynSymSet and symbolTableOffset is not None):
					self._writeDynamicSymbol(newfile, symbolTableOffset \
							+ relocEntry.r_sym * symbolEntrySize,
							dynSym.ElfN_Sym)

		# ------

		return newfile


	# this function writes the generated ELF file back
	# return values: None
	def writeElf(self, filename):

		# check if the file was completely parsed before
		if self.fileParsed is False:
			raise ValueError("Operation not possible. " \
				+ "File was not completely parsed before.")

		f = open(filename, "w")
		f.write(self.generateElf())
		f.close()


	# this function appends data to a selected segment number (if it fits)
	# return values: (int) offset in file of appended data,
	# (int) address in memory of appended data
	def appendDataToSegment(self, data, segmentNumber, addNewSection=False,
		newSectionName=None, extendExistingSection=False):

		# check if the file was completely parsed before
		if self.fileParsed is False:
			raise ValueError("Operation not possible. " \
				+ "File was not completely parsed before.")

		segmentToExtend = self.segments[segmentNumber]

		# find segment that comes directly after the segment
		# to manipulate in the virtual memory
		nextSegment, diff_p_vaddr \
			= self.getNextSegmentAndFreeSpace(segmentToExtend)

		# check if a segment exists directly after the segment
		# to manipulate in the virtual memory
		if nextSegment is None:
			# segment directly after segment to
			# manipulate does not exist in virtual memory

			# get memory address and offset in file of appended data
			newDataMemoryAddr = segmentToExtend.elfN_Phdr.p_vaddr \
				+ segmentToExtend.elfN_Phdr.p_memsz
			newDataOffset = segmentToExtend.elfN_Phdr.p_offset \
				+ segmentToExtend.elfN_Phdr.p_filesz

			# insert data
			for i in range(len(data)):
				self.data.insert((newDataOffset + i), data[i])

			# adjust offsets of all following section
			# (for example symbol sections are often behind all segments)
			for section in self.sections:
				if (section.elfN_shdr.sh_offset >=
					(segmentToExtend.elfN_Phdr.p_offset
					+ segmentToExtend.elfN_Phdr.p_filesz)):
					section.elfN_shdr.sh_offset += len(data)

			# extend size of data in file of the modifed segment
			segmentToExtend.elfN_Phdr.p_filesz += len(data)

			# extend size of data in memory of the modifed segment
			segmentToExtend.elfN_Phdr.p_memsz += len(data)


		else:
			# segment directly after segment to
			# manipulate exists in virtual memory

			# check if data to append fits
			if len(data) >= diff_p_vaddr:
				raise ValueError("Size of data to append: %d " \
					+ "Size of memory space: %d" % (len(data), diff_p_vaddr))

			# p_offset and p_vaddr are congruend modulo alignment
			# for example:
			# p_align: 0x1000 (default for LOAD segment)
			# p_offset: 0x016f88
			# p_vaddr: 0x0805ff88
			# => 0x016f88 % 0x1000 = 0xf88
			# both must have 0xf88 at the end of the address

			# get how often the appended data fits in the
			# alignment of the segment
			alignmentMultiplier = int(len(data) \
				/ segmentToExtend.elfN_Phdr.p_align) + 1

			# calculate the size to add to the offsets
			offsetAddition = alignmentMultiplier \
				* segmentToExtend.elfN_Phdr.p_align

			# adjust offsets of all following section
			for section in self.sections:
				if (section.elfN_shdr.sh_offset
					>= nextSegment.elfN_Phdr.p_offset):
					section.elfN_shdr.sh_offset += offsetAddition

			# adjust offsets of following segments
			# (ignore the directly followed segment)
			for segment in self.segments:
				if segment != segmentToExtend and segment != nextSegment:
					# use offset of the directly followed segment in order to
					# ignore segments that lies within the
					# segment to manipulate
					if (segment.elfN_Phdr.p_offset
						> nextSegment.elfN_Phdr.p_offset):
						segment.elfN_Phdr.p_offset += offsetAddition

			# adjust offset of the directly following segment of the
			# segment to manipulate
			nextSegment.elfN_Phdr.p_offset += offsetAddition

			# if program header table lies behind the segment to manipulate
			# => move it
			if (self.header.e_phoff > (segmentToExtend.elfN_Phdr.p_offset
				+ segmentToExtend.elfN_Phdr.p_filesz)):
				self.header.e_phoff += offsetAddition

			# if section header table lies behind the segment to manipulate
			# => move it
			if (self.header.e_shoff > (segmentToExtend.elfN_Phdr.p_offset
				+ segmentToExtend.elfN_Phdr.p_filesz)):
				self.header.e_shoff += offsetAddition

			# get memory address and offset in file of appended data
			newDataMemoryAddr = segmentToExtend.elfN_Phdr.p_vaddr \
				+ segmentToExtend.elfN_Phdr.p_memsz
			newDataOffset = segmentToExtend.elfN_Phdr.p_offset \
				+ segmentToExtend.elfN_Phdr.p_filesz

			# insert data
			for i in range(len(data)):
				self.data.insert((newDataOffset + i), data[i])

			# fill the rest with 0x00 until the offset addition in the
			# file is reached
			for i in range((offsetAddition - len(data))):
				self.data.insert((newDataOffset + len(data) + i), "\x00")

			# extend size of data in file of the modifed segment
			segmentToExtend.elfN_Phdr.p_filesz += len(data)

			# extend size of data in memory of the modifed segment
			segmentToExtend.elfN_Phdr.p_memsz += len(data)


		# if added data should have an own section => add new section
		if addNewSection and not extendExistingSection:

			# calculate alignment of new section
			# start with 16 as alignment (is used by .text section)
			newSectionAddrAlign = 16
			while newSectionAddrAlign != 1:
				if (len(data) % newSectionAddrAlign) == 0:
					break
				else:
					newSectionAddrAlign = newSectionAddrAlign / 2

			# add section
			# addNewSection(newSectionName, newSectionType, newSectionFlag,
			# newSectionAddr, newSectionOffset, newSectionSize,
			# newSectionLink, newSectionInfo, newSectionAddrAlign,
			# newSectionEntsize)
			self.addNewSection(newSectionName, SH_type.SHT_PROGBITS,
				(SH_flags.SHF_EXECINSTR | SH_flags.SHF_ALLOC),
				newDataMemoryAddr, newDataOffset, len(data), 0, 0,
				newSectionAddrAlign, 0)

		# if added data should extend an existing section
		# => search this section and extend it
		if extendExistingSection and not addNewSection:
			for section in self.sections:
				# the end of an existing section in the virtual
				# memory is generally equal
				# to the virtual memory address of the added data
				if ((section.elfN_shdr.sh_addr + section.elfN_shdr.sh_size)
					== newDataMemoryAddr):
					# check if data is not appended to last section
					# => use free space between segments for section
					if diff_p_vaddr is not None:
						# extend the existing section
						self.extendSection(section, diff_p_vaddr)
					else:
						# extend the existing section
						self.extendSection(section, len(data))

					break

		if not extendExistingSection and not addNewSection:
			print "NOTE: if appended data do not belong to a section they " \
				+ "will not be seen by tools that interpret sections " \
				+ "(like 'IDA 6.1.x' without the correct settings or " \
				+ "'strings' in the default configuration)."

		# return offset of appended data in file and address in memory
		return newDataOffset, newDataMemoryAddr


	# this function generates and adds a new section to the ELF file
	# return values: None
	def addNewSection(self, newSectionName, newSectionType, newSectionFlag,
		newSectionAddr, newSectionOffset, newSectionSize, newSectionLink,
		newSectionInfo, newSectionAddrAlign, newSectionEntsize):

		# check if the file was completely parsed before
		if self.fileParsed is False:
			raise ValueError("Operation not possible. " \
				+ "File was not completely parsed before.")

		# check if sections do not exist
		# => create new section header table
		if len(self.sections) == 0:

			# restore section header entry size
			if self.bits == 32:
				self.header.e_shentsize = struct.calcsize('< 2I 4I 2I 2I')
			elif self.bits == 64:
				self.header.e_shentsize = struct.calcsize('< 2I 4Q 2I 2Q')

			# when using gcc, first section is NULL section
			# => create one and add it
			# generateNewSection(sectionName, sh_name, sh_type,
			# sh_flags, sh_addr, sh_offset, sh_size, sh_link,
			# sh_info, sh_addralign, sh_entsize)
			newNullSection = self.generateNewSection("", 0, SH_type.SHT_NULL, 0,
				0, 0, 0, 0, 0, 0, 0)
			self.sections.append(newNullSection)

			# increase count of sections
			self.header.e_shnum += 1

			# create new ".shstrtab" section (section header string table)
			# and add it to the end of the file
			offsetNewShstrtab = len(self.data)
			nameNewShstrtab = ".shstrtab"

			# use third entry in new section header string table
			# as index for the new created section (name for ".shstrtab" is
			# second, name for NULL section first)
			newSectionStringTableIndex = len(nameNewShstrtab) + 1 + 1

			# generate new section object and add it
			# generateNewSection(sectionName, sh_name, sh_type,
			# sh_flags, sh_addr, sh_offset, sh_size, sh_link,
			# sh_info, sh_addralign, sh_entsize)
			newSection = self.generateNewSection(newSectionName,
				newSectionStringTableIndex, newSectionType, newSectionFlag,
				newSectionAddr, newSectionOffset, newSectionSize,
				newSectionLink, newSectionInfo, newSectionAddrAlign,
				newSectionEntsize)
			self.sections.append(newSection)

			# increase count of sections
			self.header.e_shnum += 1

			# calculate length of ".shstrtab" section
			lengthNewShstrtab = len(nameNewShstrtab) + 1 \
				+ len(newSectionName) + 1 + 1

			# generate ".shstrtab" section object and add it
			# generateNewSection(sectionName, sh_name, sh_type,
			# sh_flags, sh_addr, sh_offset, sh_size, sh_link,
			# sh_info, sh_addralign, sh_entsize)
			newShstrtabsection = self.generateNewSection(nameNewShstrtab,
				1, SH_type.SHT_STRTAB, 0,
				0, offsetNewShstrtab, lengthNewShstrtab, 0, 0, 1, 0)
			self.sections.append(newShstrtabsection)

			# increase count of sections
			self.header.e_shnum += 1

			# add section header table to the end of the file new file
			self.header.e_shoff = offsetNewShstrtab + lengthNewShstrtab

			# new section string table index is the third section
			self.header.e_shstrndx = 2


		# sections exist
		# => just add section
		else:
			# get index in the string table of the name of the new section
			# (use size of string table to just append new name to string
			# table)
			newSectionStringTableIndex \
				= self.sections[self.header.e_shstrndx].elfN_shdr.sh_size

			# generate new section object
			# generateNewSection(sectionName, sh_name, sh_type,
			# sh_flags, sh_addr, sh_offset, sh_size, sh_link,
			# sh_info, sh_addralign, sh_entsize)
			newsection = self.generateNewSection(newSectionName,
				newSectionStringTableIndex, newSectionType, newSectionFlag,
				newSectionAddr, newSectionOffset, newSectionSize,
				newSectionLink, newSectionInfo, newSectionAddrAlign,
				newSectionEntsize)

			# get position of new section
			positionNewSection = None
			for i in range(self.header.e_shnum):
				if (i+1) < self.header.e_shnum:
					if (self.sections[i].elfN_shdr.sh_offset < newSectionOffset
							and self.sections[i+1].elfN_shdr.sh_offset
							>= newSectionOffset):
						positionNewSection = i+1

						# if new section comes before string table section
						# => adjust string table section index
						if positionNewSection <= self.header.e_shstrndx:
							self.header.e_shstrndx += 1
						break
			# insert new section at calculated position
			if positionNewSection is None:
				self.sections.append(newsection)
			else:
				self.sections.insert(positionNewSection, newsection)

			# section header table lies oft directly behind the string table
			# check if new section name would overwrite data of
			# section header table
			# => move section header table
			if (self.header.e_shoff
				>= (self.sections[self.header.e_shstrndx].elfN_shdr.sh_offset
				+ self.sections[self.header.e_shstrndx].elfN_shdr.sh_size)
				and self.header.e_shoff
				<= (self.sections[self.header.e_shstrndx].elfN_shdr.sh_offset
				+ self.sections[self.header.e_shstrndx].elfN_shdr.sh_size
				+ len(newSectionName) + 1)):
				self.header.e_shoff += len(newSectionName) + 1

			# add size of new name to string table + 1 for
			# null-terminated C string
			self.sections[self.header.e_shstrndx].elfN_shdr.sh_size \
				+= len(newSectionName) + 1

			# increase count of sections
			self.header.e_shnum += 1


	# this function extends the section size by the given size
	# return values: None
	def extendSection(self, sectionToExtend, size):

		# check if the file was completely parsed before
		if self.fileParsed is False:
			raise ValueError("Operation not possible. " \
				+ "File was not completely parsed before.")

		sectionToExtend.elfN_shdr.sh_size += size


	# this function searches for a executable segment from type
	# PT_LOAD in which the data fits
	# return values: (class Segment) manipulated segment,
	# (int) offset in file of appended data,
	# (int) address in memory of appended data
	def appendDataToExecutableSegment(self, data, addNewSection=False,
		newSectionName=None, extendExistingSection=False):

		# check if the file was completely parsed before
		if self.fileParsed is False:
			raise ValueError("Operation not possible. " \
				+ "File was not completely parsed before.")

		# get all executable segments from type PT_LOAD
		possibleSegments = list()
		for segment in self.segments:
			if ((segment.elfN_Phdr.p_flags & P_flags.PF_X) == 1
				and segment.elfN_Phdr.p_type == P_type.PT_LOAD):
				possibleSegments.append(segment)

		# find space for data in all possible executable segments
		found = False
		for possibleSegment in possibleSegments:
			diff_p_vaddr = None
			# find segment that comes directly after the segment to
			# manipulate in the virtual memory
			# and get the free memory space in between
			for i in range(len(self.segments)):
				if self.segments[i] != possibleSegment:
					if ((self.segments[i].elfN_Phdr.p_vaddr
						- (possibleSegment.elfN_Phdr.p_vaddr
						+ possibleSegment.elfN_Phdr.p_memsz)) > 0):
						if (diff_p_vaddr is None
							or (self.segments[i].elfN_Phdr.p_vaddr
							- (possibleSegment.elfN_Phdr.p_vaddr
							+ possibleSegment.elfN_Phdr.p_memsz))
							< diff_p_vaddr):
							diff_p_vaddr = self.segments[i].elfN_Phdr.p_vaddr \
							- (possibleSegment.elfN_Phdr.p_vaddr \
							+ possibleSegment.elfN_Phdr.p_memsz)
				else: # get position in list of possible segment
					segmentNumber = i
			# check if data to append fits in space
			if diff_p_vaddr > len(data):
				found = True
				break
		if not found:
			raise ValueError(("Size of data to append: %d. Not enough space" \
				+ " after existing executable segment found.") % len(data))

		# append data to segment
		newDataOffset, newDataMemoryAddr = self.appendDataToSegment(data,
			segmentNumber, addNewSection=addNewSection,
			newSectionName=newSectionName,
			extendExistingSection=extendExistingSection)

		# return manipulated segment, offset of appended data in file and
		# memory address of appended data
		return self.segments[segmentNumber], newDataOffset, newDataMemoryAddr


	# this function gets the next segment of the given one and the
	# free space in memory in between
	# return values: (class Segment) next segment, (int) free space;
	# both None if no following segment was found
	def getNextSegmentAndFreeSpace(self, segmentToSearch):

		# check if the file was completely parsed before
		if self.fileParsed is False:
			raise ValueError("Operation not possible. " \
				+ "File was not completely parsed before.")

		# find segment that comes directly after the segment to
		# manipulate in the virtual memory
		diff_p_vaddr = None
		nextSegment = None
		for segment in self.segments:
			if segment != segmentToSearch:
				if ((segment.elfN_Phdr.p_vaddr
					- (segmentToSearch.elfN_Phdr.p_vaddr
					+ segmentToSearch.elfN_Phdr.p_memsz)) > 0):
					if (diff_p_vaddr is None
						or (segment.elfN_Phdr.p_vaddr
						- (segmentToSearch.elfN_Phdr.p_vaddr
						+ segmentToSearch.elfN_Phdr.p_memsz))
						< diff_p_vaddr):
						diff_p_vaddr = segment.elfN_Phdr.p_vaddr \
							- (segmentToSearch.elfN_Phdr.p_vaddr \
							+ segmentToSearch.elfN_Phdr.p_memsz)
						nextSegment = segment

		# return nextSegment and free space
		return nextSegment, diff_p_vaddr


	# this function is a wrapper function for
	# getNextSegmentAndFreeSpace(segmentToSearch)
	# which returns only the free space in memory after the segment
	# return values: (int) free space; None if no following segment was found
	def getFreeSpaceAfterSegment(self, segmentToSearch):

		# check if the file was completely parsed before
		if self.fileParsed is False:
			raise ValueError("Operation not possible. " \
				+ "File was not completely parsed before.")

		nextSegment, diff_p_vaddr \
			= self.getNextSegmentAndFreeSpace(segmentToSearch)
		return diff_p_vaddr


	# this function removes all section header entries
	# return values: None
	def removeSectionHeaderTable(self):

		# check if the file was completely parsed before
		if self.fileParsed is False:
			raise ValueError("Operation not possible. " \
				+ "File was not completely parsed before.")

		self.header.e_shoff = 0
		self.header.e_shnum = 0
		self.header.e_shentsize = 0
		self.header.e_shstrndx = Shstrndx.SHN_UNDEF
		self.sections = list()


	# this function overwrites data on the given offset
	# return values: None
	def writeDataToFileOffset(self, offset, data, force=False):

		# check if the file was completely parsed before
		if self.fileParsed is False:
			raise ValueError("Operation not possible. " \
				+ "File was not completely parsed before.")

		# get the segment to which the changed data belongs to
		segmentToManipulate = None
		for segment in self.segments:
			segStart = segment.elfN_Phdr.p_offset
			segEnd = segStart + segment.elfN_Phdr.p_filesz
			if segStart <= offset and offset < segEnd:
				segmentToManipulate = segment
				break

		# check if segment was found
		if force is False and segmentToManipulate is None:
			raise ValueError(('Segment with offset 0x%x not found ' \
				+ '(use "force=True" to ignore this check).') % offset)

		# (previous check ensures that now either force is True or segEnd has been set)
		# check if data to manipulate fits in segment
		if force is False and offset + len(data) >= segEnd:
			raise ValueError(('Size of data to manipulate: %d. Not enough ' \
				+ 'space in segment (Available: %d; use "force=True" to ' \
				+ 'ignore this check).') \
				% (len(data), (segEnd - offset)))

		# change data
		self.data[offset:offset+len(data)] = data


	# this function converts the virtual memory address to the file offset
	# return value: (int) offset in file (or None if not found)
	def virtualMemoryAddrToFileOffset(self, memoryAddr):

		# check if the file was completely parsed before
		if self.fileParsed is False:
			raise ValueError("Operation not possible. " \
				+ "File was not completely parsed before.")

		# get the segment to which the virtual memory address belongs to
		foundSegment = None
		for segment in self.segments:
			segStart = segment.elfN_Phdr.p_vaddr
			segEnd = segStart + segment.elfN_Phdr.p_memsz
			if segStart <= memoryAddr and memoryAddr < segEnd:
				foundSegment = segment
				break

		# check if segment was found
		if foundSegment is None:
			return None

		relOffset = memoryAddr - foundSegment.elfN_Phdr.p_vaddr
		# relOffset >= 0 due to condition in segment search loop

		# check if file is mapped 1:1 to memory
		if foundSegment.elfN_Phdr.p_filesz != foundSegment.elfN_Phdr.p_memsz:
			# check if the memory address relative to the virtual memory
			# address of the segment lies within the file size of the segment
			if relOffset >= foundSegment.elfN_Phdr.p_filesz:
				raise ValueError("Can not convert virtual memory address " \
					+ "to file offset.")

		return foundSegment.elfN_Phdr.p_offset + relOffset


	# this function converts the file offset to the virtual memory address
	# return value: (int) virtual memory address (or None if not found)
	def fileOffsetToVirtualMemoryAddr(self, offset):

		# check if the file was completely parsed before
		if self.fileParsed is False:
			raise ValueError("Operation not possible. " \
				+ "File was not completely parsed before.")

		# get the segment to which the file offset belongs to
		foundSegment = None
		for segment in self.segments:
			segStart = segment.elfN_Phdr.p_offset
			segEnd = segStart + segment.elfN_Phdr.p_filesz
			if segStart <= offset and offset < segEnd:
				foundSegment = segment
				break

		# check if segment was found
		if foundSegment is None:
			return None

		relOffset = offset - foundSegment.elfN_Phdr.p_offset
		# relOffset >= 0 due to condition in segment search loop

		# check if file is mapped 1:1 to memory
		if foundSegment.elfN_Phdr.p_filesz != foundSegment.elfN_Phdr.p_memsz:
			if relOffset >= foundSegment.elfN_Phdr.p_memsz:
				raise ValueError("Data not mapped 1:1 from file to memory." \
					+ " Can not convert virtual memory address to file offset.")

		return foundSegment.elfN_Phdr.p_vaddr + relOffset


	# this function overwrites an entry in the got
	# (global offset table) in the file
	# return values: None
	def modifyGotEntryAddr(self, name, memoryAddr):

		# check if the file was completely parsed before
		if self.fileParsed is False:
			raise ValueError("Operation not possible. " \
				+ "File was not completely parsed before.")

		# search for name in jump relocation entries
		entryToModify = None
		for jmpEntry in self.jumpRelocationEntries:
			if jmpEntry.name == name:
				entryToModify = jmpEntry
				break
		if entryToModify is None:
			raise ValueError('Jump relocation entry with the name' \
				+ ' "%s" was not found.' % name)

		# calculate file offset of got
		entryOffset = self.virtualMemoryAddrToFileOffset(
			entryToModify.r_offset)

		# generate list with new memory address for got
		if self.bits == 32:
			fmt = '<I'
		elif self.bits == 64:
			fmt = '<Q'
		newGotAddr = struct.pack(fmt, memoryAddr)

		# overwrite old offset
		self.writeDataToFileOffset(entryOffset, newGotAddr)


	# this function gets the value of the got (global offset table) entry
	# (a memory address to jump to)
	# return values: (int) value (memory address) of got entry
	def getValueOfGotEntry(self, name):

		# check if the file was completely parsed before
		if self.fileParsed is False:
			raise ValueError("Operation not possible. " \
				+ "File was not completely parsed before.")

		# search for name in jump relocation entries
		entryToModify = None
		for jmpEntry in self.jumpRelocationEntries:
			if jmpEntry.name == name:
				entryToModify = jmpEntry
				break
		if entryToModify is None:
			raise ValueError('Jump relocation entry with the name' \
				+ ' "%s" was not found.' % name)

		# calculate file offset of got
		entryOffset = self.virtualMemoryAddrToFileOffset(
			entryToModify.r_offset)

		if self.bits == 32:
			fmt = '<I'
		elif self.bits == 64:
			fmt = '<Q'
		fmtSize = struct.calcsize(fmt)
		return struct.unpack(fmt, self.data[entryOffset:entryOffset+fmtSize])[0]


	# this function gets the memory address of the got
	# (global offset table) entry
	# return values: (int) memory address of got entry
	def getMemAddrOfGotEntry(self, name):

		# check if the file was completely parsed before
		if self.fileParsed is False:
			raise ValueError("Operation not possible. " \
				+ "File was not completely parsed before.")

		# search for name in jump relocation entries
		entryToSearch = None
		for jmpEntry in self.jumpRelocationEntries:
			if jmpEntry.name == name:
				entryToSearch = jmpEntry
				break
		if entryToSearch is None:
			raise ValueError('Jump relocation entry with the name' \
				+ ' "%s" was not found.' % name)

		return entryToSearch.r_offset


	# this functions removes the first section given by name
	# return values: None
	def deleteSectionByName(self, name):

		# check if the file was completely parsed before
		if self.fileParsed is False:
			raise ValueError("Operation not possible. " \
				+ "File was not completely parsed before.")

		# search for the first section with the given name
		found = False
		for sectionNo in range(len(self.sections)):
			if self.sections[sectionNo].sectionName == name:
				found = True
				break

		# check if the section was found
		if not found:
			return

		# remove the found section
		self.sections.pop(sectionNo)

		# modify ELF header
		# => change section string table index and number of sections
		if sectionNo < self.header.e_shstrndx:
			self.header.e_shstrndx = self.header.e_shstrndx - 1
		elif sectionNo == self.header.e_shstrndx:
			self.header.e_shstrndx = 0
		self.header.e_shnum = self.header.e_shnum - 1


	# this function searches for the first jump relocation entry given by name
	# return values: (ElfN_Rel) jump relocation entry
	def getJmpRelEntryByName(self, name):

		# check if the file was completely parsed before
		if self.fileParsed is False:
			raise ValueError("Operation not possible. " \
				+ "File was not completely parsed before.")

		# search for the first jump relocation entry with the given name
		foundEntry = None
		for jmpRelEntry in self.jumpRelocationEntries:
			if jmpRelEntry.symbol.symbolName == name:
				foundEntry = jmpRelEntry
				break

		# check if jump relocation entry was found
		if foundEntry is None:
			raise ValueError('Jump relocation entry with the name' \
				+ ' "%s" was not found.' % name)

		return foundEntry
